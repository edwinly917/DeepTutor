export type SlideLayout =
  | "SPLIT_RIGHT"
  | "SPLIT_LEFT"
  | "TOP_IMAGE"
  | "TYPOGRAPHIC"
  | "SECTION_HEADER"
  | "QUOTE"
  | "OVERVIEW"
  | "SPLIT_IMAGE_LEFT"
  | "SPLIT_IMAGE_RIGHT"
  | "TYPOGRAPHIC_WITH_IMAGE";

export interface SlideContent {
  title: string;
  points: string[];
  imagePrompt?: string;
  generatedImageUrl?: string;
  layout: SlideLayout;
  iconName?: string;
  pageId?: string;
  status?: string;
  isDirty?: boolean;
  descriptionText?: string | null;
}

export interface PresentationOutline {
  title: string;
  subtitle: string;
  themeColor: string;
  accentColor: string;
  slides: SlideContent[];
}

export type PptCreationMode =
  | "auto"
  | "from_research"
  | "from_notebook"
  | "from_sources";

export interface PptProjectPage {
  id: string;
  project_id: string;
  order_index: number;
  part?: string | null;
  outline_content: {
    title: string;
    points: string[];
  };
  description_content?: {
    text?: string;
    generated_at?: string | null;
    detail_level?: string | null;
  } | null;
  image_prompt?: string | null;
  generated_image_path?: string | null;
  cached_image_path?: string | null;
  is_dirty?: boolean;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PptTask {
  id: string;
  project_id: string;
  task_type: string;
  status: string;
  progress: {
    current?: number;
    total?: number;
    percentage?: number;
    message?: string;
    phase?: string | null;
    warnings?: string[];
    failed_count?: number;
    download_url?: string | null;
    page_ids?: string[];
  };
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  finished_at?: string | null;
}

export interface PptSlideChatMessage {
  id: string;
  page_id: string;
  role: string;
  content: string;
  edit_type?: string | null;
  created_at?: string | null;
}

export interface PptProject {
  id: string;
  notebook_id?: string | null;
  session_id?: string | null;
  creation_type: "from_research" | "from_notebook" | "from_sources";
  source_content?: string | null;
  style_preset_id?: string | null;
  style_custom_text?: string | null;
  template_image_path?: string | null;
  template_file_refs?: Array<Record<string, unknown>>;
  reference_style_prompt?: string | null;
  reference_layout_prompt?: string | null;
  reference_content_prompt?: string | null;
  image_aspect_ratio: "16:9" | "4:3";
  language: string;
  reference_sources: Array<Record<string, unknown>>;
  source_refs?: Array<Record<string, unknown>>;
  normalized_content?: string | null;
  content_cached_at?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  pages: PptProjectPage[];
  tasks?: PptTask[];
  presentation_outline: PresentationOutline;
}

export interface PptConfigResponse {
  enabled: boolean;
  max_slides: number;
  style_presets: Array<{
    id: string;
    name_zh: string;
    name_en: string;
    color: string;
    description_zh: string;
    description_en: string;
  }>;
  polling_hint_ms: number;
  creation_modes: PptCreationMode[];
}

export interface PptReferenceImageUploadResponse {
  image_path: string;
  image_url: string;
  image_name: string;
  derived_style_prompt: string;
  derived_layout_prompt?: string;
  derived_content_prompt?: string;
  content_type?: string;
}

export enum AppState {
  IDLE = "IDLE",
  GENERATING_OUTLINE = "GENERATING_OUTLINE",
  GENERATING_IMAGES = "GENERATING_IMAGES",
  REVIEWING = "REVIEWING",
  EXPORTING = "EXPORTING",
}
