import { createContext, Fragment, useContext, useState, type ReactNode } from "react";
import { getAt, joinPath, resolve, setAt, type BoundValue, type SurfaceState, type UserAction } from "./model";
import { catalog } from "./catalog";

interface Ctx {
  surface: SurfaceState;
  data: any;
  setValue: (path: string, value: unknown) => void;
  act: (sourceId: string, action: { name: string; context?: { key: string; value: BoundValue }[] }, scope: string) => void;
  pending: boolean;
}

const SurfaceContext = createContext<Ctx | null>(null);

export function useSurface(): Ctx {
  const ctx = useContext(SurfaceContext);
  if (!ctx) throw new Error("A2UI component rendered outside a surface");
  return ctx;
}

/** Value of a BoundValue in the current scope. */
export function useBound(bound: BoundValue | undefined, scope: string): any {
  const { data } = useSurface();
  return resolve(bound, data, scope);
}

/** Absolute data path for a bound input, or null for literal-only values. */
export function boundPath(bound: BoundValue | undefined, scope: string): string | null {
  return bound?.path !== undefined ? joinPath(scope, bound.path) : null;
}

export function Node({ id, scope }: { id: string; scope: string }): ReactNode {
  const { surface } = useSurface();
  const def = surface.components[id];
  if (!def) return null;
  const Component = catalog[def.type];
  if (!Component) {
    console.warn(`A2UI: component type "${def.type}" is not in the catalog`);
    return null;
  }
  return <Component id={id} props={def.props} scope={scope} />;
}

/** Children of a container: explicit list, or a template repeated over a data array. */
export function Children({ spec, scope, item }: { spec: any; scope: string; item?: "li" }): ReactNode {
  const { data } = useSurface();
  const wrap = (key: string, node: ReactNode) => (item ? <li key={key}>{node}</li> : <Fragment key={key}>{node}</Fragment>);
  if (spec?.explicitList) return spec.explicitList.map((cid: string) => wrap(cid, <Node id={cid} scope={scope} />));
  if (spec?.template) {
    const base = joinPath(scope, spec.template.dataBinding);
    const items = getAt(data, base);
    const keys = Array.isArray(items) ? items.map((_, i) => String(i)) : Object.keys(items ?? {});
    return keys.map((k) => wrap(k, <Node id={spec.template.componentId} scope={`${base}/${k}`} />));
  }
  return null;
}

interface Props {
  surface: SurfaceState;
  onAction: (action: UserAction) => Promise<void>;
}

export default function Surface({ surface, onAction }: Props) {
  // Local copy of the data model: inputs write here until an action sends it back.
  const [data, setData] = useState(surface.data);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ctx: Ctx = {
    surface,
    data,
    pending,
    setValue: (path, value) => setData((d: any) => setAt(d, path, value)),
    act: (sourceId, action, scope) => {
      if (pending) return;
      const context: Record<string, unknown> = {};
      for (const { key, value } of action.context ?? []) context[key] = resolve(value, data, scope);
      setPending(true);
      setError(null);
      onAction({
        name: action.name,
        surfaceId: surface.id,
        sourceComponentId: sourceId,
        timestamp: new Date().toISOString(),
        context,
      })
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "The action failed."))
        .finally(() => setPending(false));
    },
  };

  if (!surface.root) return null;
  return (
    <SurfaceContext.Provider value={ctx}>
      <section className={`gu-surface${pending ? " is-pending" : ""}`} aria-busy={pending}>
        <Node id={surface.root} scope="" />
        {error && (
          <p className="gu-error" role="alert">
            {error}
          </p>
        )}
      </section>
    </SurfaceContext.Provider>
  );
}
