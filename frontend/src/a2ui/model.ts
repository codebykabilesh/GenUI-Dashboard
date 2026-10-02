// A2UI v0.8 client-side model: folds server messages into renderable surfaces.

export type BoundValue = {
  literalString?: string;
  literalNumber?: number;
  literalBoolean?: boolean;
  path?: string;
};

export interface ComponentDef {
  id: string;
  type: string;
  props: Record<string, any>;
}

export type A2UIMessage =
  | { surfaceUpdate: { surfaceId: string; components: { id: string; component: Record<string, any> }[] } }
  | { dataModelUpdate: { surfaceId: string; path?: string; contents: DataEntry[] } }
  | { beginRendering: { surfaceId: string; root: string; catalogId?: string } }
  | { deleteSurface: { surfaceId: string } };

export interface DataEntry {
  key: string;
  valueString?: string;
  valueNumber?: number;
  valueBoolean?: boolean;
  valueMap?: DataEntry[];
}

export interface SurfaceState {
  id: string;
  components: Record<string, ComponentDef>;
  data: Record<string, any>;
  root: string | null;
  catalogId?: string;
  /** Increments on every beginRendering, so local input state resets when the server re-renders. */
  version: number;
}

export interface UserAction {
  name: string;
  surfaceId: string;
  sourceComponentId: string;
  timestamp: string;
  context: Record<string, unknown>;
}

/** Adjacency-list contents -> plain JS. A map whose keys are 0..n-1 becomes an array. */
export function fromContents(entries: DataEntry[]): any {
  const obj: Record<string, any> = {};
  for (const e of entries) {
    if (e.valueMap !== undefined) obj[e.key] = fromContents(e.valueMap);
    else if (e.valueString !== undefined) obj[e.key] = e.valueString;
    else if (e.valueNumber !== undefined) obj[e.key] = e.valueNumber;
    else if (e.valueBoolean !== undefined) obj[e.key] = e.valueBoolean;
  }
  const keys = Object.keys(obj);
  if (keys.length > 0 && keys.every((k, i) => k === String(i))) return keys.map((k) => obj[k]);
  return obj;
}

const segments = (path: string) => path.split("/").filter(Boolean);

export function joinPath(scope: string, path: string): string {
  return path.startsWith("/") ? path : `${scope.replace(/\/$/, "")}/${path}`;
}

export function getAt(data: any, path: string): any {
  return segments(path).reduce((node, key) => (node == null ? undefined : node[key]), data);
}

export function setAt(data: any, path: string, value: any): any {
  const keys = segments(path);
  if (keys.length === 0) return value;
  const [head, ...rest] = keys;
  const base = Array.isArray(data) ? [...data] : { ...(data ?? {}) };
  (base as any)[head] = setAt(data?.[head], "/" + rest.join("/"), value);
  return base;
}

export function resolve(bound: BoundValue | undefined, data: any, scope: string): any {
  if (!bound) return undefined;
  if (bound.path !== undefined) {
    const v = getAt(data, joinPath(scope, bound.path));
    if (v !== undefined) return v;
  }
  return bound.literalString ?? bound.literalNumber ?? bound.literalBoolean;
}

/** Fold a message list into surfaces, in order of first appearance. */
export function reduceMessages(messages: A2UIMessage[]): SurfaceState[] {
  const surfaces = new Map<string, SurfaceState>();
  const get = (id: string) => {
    let s = surfaces.get(id);
    if (!s) {
      s = { id, components: {}, data: {}, root: null, version: 0 };
      surfaces.set(id, s);
    }
    return s;
  };
  for (const msg of messages) {
    if ("surfaceUpdate" in msg) {
      const s = get(msg.surfaceUpdate.surfaceId);
      for (const c of msg.surfaceUpdate.components) {
        const [type, props] = Object.entries(c.component)[0] ?? [];
        if (type) s.components = { ...s.components, [c.id]: { id: c.id, type, props } };
      }
    } else if ("dataModelUpdate" in msg) {
      const s = get(msg.dataModelUpdate.surfaceId);
      const value = fromContents(msg.dataModelUpdate.contents);
      s.data = msg.dataModelUpdate.path ? setAt(s.data, msg.dataModelUpdate.path, value) : { ...s.data, ...value };
    } else if ("beginRendering" in msg) {
      const s = get(msg.beginRendering.surfaceId);
      s.root = msg.beginRendering.root;
      s.catalogId = msg.beginRendering.catalogId;
      s.version += 1;
    } else if ("deleteSurface" in msg) {
      surfaces.delete(msg.deleteSurface.surfaceId);
    }
  }
  return [...surfaces.values()].filter((s) => s.root);
}
