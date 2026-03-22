import { apiUrl } from "@/lib/api";
import {
  PptConfigResponse,
  PptProject,
  PptReferenceImageUploadResponse,
  PptSlideChatMessage,
  PptTask,
} from "@/types/ppt";

type JsonValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | JsonValue[]
  | { [key: string]: JsonValue };
type JsonPayload = { [key: string]: JsonValue | undefined };

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const payload = (await res.json()) as { detail?: string };
      if (payload?.detail) {
        detail = payload.detail;
      }
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function fetchPptConfig(): Promise<PptConfigResponse> {
  const res = await fetch(apiUrl("/api/v1/ppt/config"));
  return readJson<PptConfigResponse>(res);
}

export async function uploadPptReferenceImage(
  file: File,
): Promise<PptReferenceImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(apiUrl("/api/v1/ppt/reference-images"), {
    method: "POST",
    body: formData,
  });
  return readJson<PptReferenceImageUploadResponse>(res);
}

export async function previewPptStyle(
  stylePrompt?: string,
): Promise<{ preview_svg?: string }> {
  const res = await fetch(apiUrl("/api/v1/ppt/style-preview"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ style_prompt: stylePrompt || undefined }),
  });
  return readJson<{ preview_svg?: string }>(res);
}

export async function createPptProject(
  payload: JsonPayload,
): Promise<PptProject> {
  const res = await fetch(apiUrl("/api/v1/ppt/projects"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson<PptProject>(res);
}

export async function fetchPptProject(projectId: string): Promise<PptProject> {
  const res = await fetch(apiUrl(`/api/v1/ppt/projects/${projectId}`));
  return readJson<PptProject>(res);
}

export async function generatePptOutline(
  projectId: string,
  stylePrompt?: string,
  maxSlides?: number,
): Promise<PptProject> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/generate/outline`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        style_prompt: stylePrompt || undefined,
        max_slides: maxSlides,
      }),
    },
  );
  return readJson<PptProject>(res);
}

export async function generatePptDescriptions(
  projectId: string,
  pageIds?: string[],
  detailLevel = "default",
): Promise<PptTask> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/generate/descriptions`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_ids: pageIds,
        detail_level: detailLevel,
      }),
    },
  );
  return readJson<PptTask>(res);
}

export async function generatePptImages(
  projectId: string,
  pageIds?: string[],
): Promise<PptTask> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/generate/images`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_ids: pageIds }),
    },
  );
  return readJson<PptTask>(res);
}

export async function generatePptFull(
  projectId: string,
  options?: {
    style_prompt?: string;
    max_slides?: number;
    detail_level?: "concise" | "default" | "detailed";
  },
): Promise<PptTask> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/generate/full`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options || {}),
    },
  );
  return readJson<PptTask>(res);
}

export async function fetchPptTask(
  projectId: string,
  taskId: string,
): Promise<PptTask> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/tasks/${taskId}`),
  );
  return readJson<PptTask>(res);
}

export async function updatePptPage(
  projectId: string,
  pageId: string,
  payload: {
    title?: string;
    points?: string[];
    description_text?: string;
    image_prompt?: string;
  },
) {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/pages/${pageId}`),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return readJson(res);
}

export async function regeneratePptPageImage(
  projectId: string,
  pageId: string,
): Promise<PptTask> {
  const res = await fetch(
    apiUrl(
      `/api/v1/ppt/projects/${projectId}/pages/${pageId}/regenerate-image`,
    ),
    { method: "POST" },
  );
  return readJson<PptTask>(res);
}

export async function chatEditPptPage(
  projectId: string,
  pageId: string,
  message: string,
): Promise<{
  task: PptTask;
  edit_type: string;
  assistant_message: string;
}> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/pages/${pageId}/chat`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    },
  );
  return readJson<{
    task: PptTask;
    edit_type: string;
    assistant_message: string;
  }>(res);
}

export async function fetchPptPageChatHistory(
  projectId: string,
  pageId: string,
): Promise<{
  messages: PptSlideChatMessage[];
}> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/pages/${pageId}/chat-history`),
  );
  return readJson<{ messages: PptSlideChatMessage[] }>(res);
}

export async function exportPptProjectPptx(
  projectId: string,
): Promise<{ download_url: string; filename: string }> {
  const res = await fetch(
    apiUrl(`/api/v1/ppt/projects/${projectId}/export/pptx`),
  );
  return readJson<{ download_url: string; filename: string }>(res);
}
