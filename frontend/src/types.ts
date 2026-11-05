export type Object3DData = {
  id: string;
  name: string;
  type: string;
  parent: string | null;
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
  visible: boolean;
  locked?: boolean;
  source_id?: string;
  material?: PBR;
  anchor?: "center" | "bottom";
  relation?:
    | "left_of"
    | "right_of"
    | "in_front_of"
    | "behind"
    | "above"
    | "below"
    | "next_to"
    | null;
  reference_object_id?: string | null;
  spacing?: number;
  parameters: Record<
    string,
    string | number | boolean | null | Record<string, unknown>
  >;
};
export type PBR = {
  baseColor: string;
  metalness: number;
  roughness: number;
  opacity: number;
  transparent: boolean;
  doubleSided: boolean;
  emissive: string;
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
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  error: string | null;
  model_id?: string;
};
export type Project = {
  id: string;
  name: string;
  scene: string;
  prompt: string;
  updated: string;
  model_id: string | null;
};
export type ModelStats = {
  meshes: number;
  vertices?: number;
  triangles?: number;
  glb_bytes?: number;
};
export type ModelAsset = {
  id: string;
  stats: ModelStats;
  scene: Scene;
  url: string;
};
