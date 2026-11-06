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
  asset?: AssetMetadata | null;
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
export type AssetMetadata = {
  asset_id: string;
  generator: string;
  model_version: string;
  source_prompt: string;
  source_image: string | null;
  generated_at: string;
  geometry_format: "GLB";
  texture_assets: { slot: string; source: string }[];
  license_metadata: { name?: string; source?: string; restrictions?: string[] };
  provenance: {
    kind: "real_ai" | "mock";
    operation?: string;
    sha256?: string;
    source?: string;
    source_revision?: string;
  };
};
export type AIEngine = {
  id: string;
  name: string;
  version: string;
  is_mock: boolean;
  models: string[];
  texture_capability: string;
  license: { name: string; source: string; restrictions: string[] };
  requirements: Record<string, unknown>;
};
export type AIImage = {
  id: string;
  url: string;
  info: { width: number; height: number; format: string; bytes: number };
  prompt?: string;
};
export type AIJob = {
  id: string;
  engine: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  stage: string;
  progress: number | null;
  progress_kind: "stage" | "diffusion_steps" | "provider";
  remote_id?: string | null;
  error: string | null;
  is_mock: boolean;
  asset_id: string | null;
  model_url: string | null;
  original_available: boolean;
  stats:
    | (ModelStats & {
        bounds: number[][];
        texture_status: string;
        texture_support: Record<string, boolean>;
        processing?: { before: ModelStats; after: ModelStats; notes: string[] };
      })
    | null;
  metadata: AssetMetadata | null;
  created: string;
};
