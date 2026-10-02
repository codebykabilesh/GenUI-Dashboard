import { useEffect, useMemo, useRef, useState } from "react";
import { AppBridge, PostMessageTransport } from "@modelcontextprotocol/ext-apps/app-bridge";
import { callTool, type UIResource } from "../api";

const MIN_HEIGHT = 40;
const MAX_HEIGHT = 1200;

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** Inject the server-declared CSP into the view's HTML (the iframe is an opaque-origin sandbox). */
function withCsp(html: string, csp: UIResource["csp"]): string {
  const res = (csp?.resourceDomains ?? []).join(" ");
  const connect = (csp?.connectDomains ?? []).join(" ");
  const frames = (csp?.frameDomains ?? []).join(" ") || "'none'";
  const policy = [
    "default-src 'none'",
    `script-src 'unsafe-inline' 'wasm-unsafe-eval' ${res}`,
    `style-src 'unsafe-inline' ${res}`,
    `img-src data: blob: ${res}`,
    `font-src data: ${res}`,
    `connect-src ${connect || "'none'"}`,
    `frame-src ${frames}`,
  ].join("; ");
  const meta = `<meta http-equiv="Content-Security-Policy" content="${policy}">`;
  return /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, (m) => `${m}${meta}`) : meta + html;
}

function toolResultPayload(result: unknown) {
  return {
    content: [{ type: "text" as const, text: typeof result === "string" ? result : JSON.stringify(result) }],
    ...(isObject(result) ? { structuredContent: result } : {}),
  };
}

/** Renders one MCP App view (e.g. a Prefab generative UI) in a sandboxed iframe via AppBridge. */
export default function McpAppView({ ui }: { ui: UIResource }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(MIN_HEIGHT);
  const [error, setError] = useState<string | null>(null);
  const srcDoc = useMemo(() => withCsp(ui.html, ui.csp), [ui.html, ui.csp]);

  useEffect(() => {
    const frame = iframeRef.current?.contentWindow;
    if (!frame) return;

    const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    const bridge = new AppBridge(
      null,
      { name: "genui-dashboard", version: "0.1.0" },
      { openLinks: {}, serverTools: {} },
      { hostContext: { theme: dark ? "dark" : "light", displayMode: "inline" } },
    );

    bridge.oninitialized = () => {
      void bridge.sendToolInput({ arguments: ui.tool_input });
      void bridge.sendToolResult(toolResultPayload(ui.tool_result));
    };
    bridge.onsizechange = ({ height: h }) => {
      if (typeof h === "number") setHeight(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.ceil(h))));
    };
    // The view may only call tools of the server it came from.
    bridge.oncalltool = async ({ name, arguments: args }) => {
      try {
        const result = await callTool(`${ui.server}__${name}`, args ?? {});
        return toolResultPayload(result);
      } catch (e) {
        return { content: [{ type: "text", text: e instanceof Error ? e.message : "Tool call failed" }], isError: true };
      }
    };
    bridge.onopenlink = async ({ url }) => {
      if (/^https?:\/\//i.test(url)) window.open(url, "_blank", "noopener,noreferrer");
      return {};
    };

    bridge.connect(new PostMessageTransport(frame, frame)).catch((e) => {
      console.error("MCP App bridge failed:", e);
      setError("Could not start the interactive view.");
    });

    return () => {
      void bridge.close();
    };
  }, [ui]);

  return (
    <div className="mcp-app">
      <iframe
        ref={iframeRef}
        title={`${ui.tool_name} view`}
        sandbox="allow-scripts"
        srcDoc={srcDoc}
        style={{ height }}
      />
      {error && <div className="mcp-app-error">{error}</div>}
    </div>
  );
}
