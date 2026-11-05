import { useState } from "react";
import { exportGLTF, exportOBJ, saveBlob } from "../services/export";
export function ExportPanel({
  enabled,
  onError,
}: {
  enabled: boolean;
  onError: (s: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  async function run(kind: string) {
    setBusy(true);
    try {
      if (kind === "obj") {
        const result = exportOBJ();
        saveBlob(result.obj, "model.obj", "text/plain");
        saveBlob(result.mtl, "model.mtl", "text/plain");
      } else {
        const result = await exportGLTF(kind === "glb");
        saveBlob(
          result instanceof ArrayBuffer ? result : JSON.stringify(result),
          kind === "glb" ? "model.glb" : "model.gltf",
        );
      }
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {["glb", "gltf", "obj"].map((k) => (
        <button key={k} disabled={!enabled || busy} onClick={() => run(k)}>
          ↓ {k.toUpperCase()}
        </button>
      ))}
    </>
  );
}
