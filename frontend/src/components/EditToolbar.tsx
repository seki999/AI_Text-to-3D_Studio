import { useEffect } from "react";
import { useStudio } from "../store";
import type { EditingOptions } from "../viewer/EditingControls";
export function EditToolbar({
  options,
  setOptions,
}: {
  options: EditingOptions;
  setOptions: (v: EditingOptions) => void;
}) {
  useEffect(() => {
    function key(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target.closest("input,textarea,select,[contenteditable=true]"))
        return;
      const s = useStudio.getState();
      if (e.ctrlKey || e.metaKey) {
        if (e.key.toLowerCase() === "z") {
          e.preventDefault();
          e.shiftKey ? s.redo() : s.undo();
        }
        if (e.key.toLowerCase() === "y") {
          e.preventDefault();
          s.redo();
        }
        return;
      }
      const modes: Record<string, EditingOptions["mode"]> = {
        w: "translate",
        e: "rotate",
        r: "scale",
      };
      if (modes[e.key.toLowerCase()])
        setOptions({ ...options, mode: modes[e.key.toLowerCase()] });
      if (e.key === "Delete") {
        e.preventDefault();
        s.remove();
      }
      if (e.key.toLowerCase() === "f")
        setOptions({ ...options, focus: options.focus + 1 });
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [options, setOptions]);
  return (
    <div className="edit-toolbar">
      {(["translate", "rotate", "scale"] as const).map((mode, i) => (
        <button
          key={mode}
          className={options.mode === mode ? "active" : ""}
          onClick={() => setOptions({ ...options, mode })}
        >
          {["移动 W", "旋转 E", "缩放 R"][i]}
        </button>
      ))}
      <select
        aria-label="变换空间"
        value={options.space}
        onChange={(e) =>
          setOptions({ ...options, space: e.target.value as "local" | "world" })
        }
      >
        <option value="world">World</option>
        <option value="local">Local</option>
      </select>
      <label>
        <input
          type="checkbox"
          checked={options.snap}
          onChange={(e) => setOptions({ ...options, snap: e.target.checked })}
        />
        吸附 .5m / 15°
      </label>
      <button onClick={() => useStudio.getState().duplicate()}>复制选中</button>
      <button onClick={() => useStudio.getState().remove()}>删除选中</button>
    </div>
  );
}
