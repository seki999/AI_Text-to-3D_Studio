import * as T from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { snapshot, getExportModel, exportGLTF } from "./export";
import { applyTransform, disposeModel } from "../engines/native";
import { useStudio } from "../store";
import type { ModelAsset } from "../types";
import { api } from "../api";

export async function prepareAssetInsertion(assetId: string) {
  const asset = await api<ModelAsset>("/models/" + assetId);
  const loaded = await new GLTFLoader().loadAsync(asset.url);
  if (asset.scene.objects[0]?.asset?.generator === "meshy") {
    // Keep provider asset declarations in exported GLB extras as well as the raw backup.
    loaded.scene.userData.provider_gltf_asset = structuredClone(
      loaded.parser.json.asset,
    );
  }
  const state = useStudio.getState(),
    originalScene = state.scene,
    current = getExportModel();
  const combined = new T.Group();
  combined.name = "Studio Model";
  let currentCopy: T.Group | null = null;
  try {
    if (originalScene.objects.length && !current)
      throw Error(
        "请先生成当前参数场景，再插入 AI 资产；或点击新建使用空场景。",
      );
    if (current) {
      currentCopy = snapshot(current, true);
      combined.add(currentCopy);
    }
    const object = structuredClone(asset.scene.objects[0]);
    if (originalScene.objects.some((o) => o.id === object.id))
      object.id = "asset_" + crypto.randomUUID();
    if (current) {
      const prior = new T.Box3().setFromObject(current),
        incoming = new T.Box3().setFromObject(loaded.scene);
      object.position[0] =
        prior.max.x + (incoming.max.x - incoming.min.x) / 2 + 0.5;
    }
    const wrapper = new T.Group();
    wrapper.name = object.id;
    wrapper.userData.editorId = object.id;
    wrapper.userData.asset_metadata = object.asset;
    wrapper.add(loaded.scene);
    applyTransform(wrapper, object);
    combined.add(wrapper);
    combined.updateMatrixWorld(true);
    const binary = (await exportGLTF(true, combined, true)) as ArrayBuffer;
    if (useStudio.getState().scene !== originalScene)
      throw Error("插入期间场景发生变化，请重试以保留最新编辑。");
    if (originalScene.objects.length >= 50)
      throw Error("场景已达到 50 个对象上限");
    return {
      url: URL.createObjectURL(
        new Blob([binary], { type: "model/gltf-binary" }),
      ),
      scene: {
        ...originalScene,
        name: originalScene.objects.length
          ? originalScene.name
          : asset.scene.name,
        objects: [...originalScene.objects, object],
      },
      selected: object.id,
    };
  } finally {
    disposeModel(loaded.scene);
    currentCopy?.traverse((node) => {
      if (node instanceof T.Mesh)
        for (const mat of Array.isArray(node.material)
          ? node.material
          : [node.material])
          mat.dispose();
    });
  }
}
