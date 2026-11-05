import { useState } from "react";
import { api } from "../api";
type Info = {
  used_bytes: number;
  max_bytes: number;
  retention_days: number;
  assets: { id: string; bytes: number; protected: boolean }[];
};
export function StoragePanel() {
  const [info, setInfo] = useState<Info | null>(null),
    [message, setMessage] = useState(""),
    [days, setDays] = useState(30);
  const refresh = async () => {
    try {
      setInfo(await api("/storage"));
    } catch (e) {
      setMessage(String(e));
    }
  };
  return (
    <section>
      <div className="section-title spaced">本地磁盘缓存</div>
      <button onClick={refresh}>查看磁盘使用量</button>
      {info && (
        <>
          <p className="muted tiny">
            {(info.used_bytes / 1048576).toFixed(2)} /{" "}
            {(info.max_bytes / 1048576).toFixed(0)} MB
            <br />
            {info.assets.filter((a) => a.protected).length}{" "}
            个项目引用的资产受到保护
          </p>
          <label>清理早于多少天的缓存</label>
          <input
            aria-label="缓存保留天数"
            type="number"
            min="0"
            max="3650"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          />
          <button
            onClick={async () => {
              try {
                const r = await api<{ released_bytes: number }>(
                  "/storage/cleanup",
                  "POST",
                  { older_than_days: days },
                );
                setMessage(
                  "已释放 " + (r.released_bytes / 1048576).toFixed(2) + " MB",
                );
                refresh();
              } catch (e) {
                setMessage(String(e));
              }
            }}
          >
            清理未引用缓存
          </button>
        </>
      )}
      <p className="muted tiny">{message}</p>
    </section>
  );
}
