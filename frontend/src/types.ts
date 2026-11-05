export type Object3DData = {
  id: string;
  name: string;
  type: string;
  parent: string | null;
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
  visible: boolean;
  parameters: Record<string, string | number | boolean>;
};
export type Scene = {
  version: "1.0";
  name: string;
  units: "meters";
  objects: Object3DData[];
  environment: { ground: boolean; background: string };
};
export type Job = {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  error: string | null;
  model_id?: string;
};
