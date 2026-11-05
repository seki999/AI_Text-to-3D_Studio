import { useStudio } from "../store";
export function SceneTree() {
  const { scene, selection, select } = useStudio();
  return (
    <>
      {" "}
      <div className="section-title">
        场景对象 <span>{String(scene.objects.length).padStart(2, "0")}</span>
      </div>
      <div className="tree">
        <p className="muted tiny">▾ {scene.name}</p>
        {scene.objects.map((o) => (
          <button
            className={selection.includes(o.id) ? "selected" : ""}
            key={o.id}
            onClick={(e) => select(o.id, e.shiftKey)}
          >
            <span>{o.locked ? "▣" : "◇"}</span>
            {o.name}
            <small>{o.type}</small>
          </button>
        ))}
        {!scene.objects.length && (
          <p className="muted tiny">解析描述后，对象将在这里显示</p>
        )}
      </div>
    </>
  );
}
