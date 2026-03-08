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
  descriptionText?: string | null;
}

export interface PresentationOutline {
  title: string;
  subtitle: string;
  themeColor: string;
  accentColor: string;
  slides: SlideContent[];
}

export type PptCreationMode = "auto" | "idea" | "outline" | "descriptions";

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
    warnings?: string[];
    failed_count?: number;
    download_url?: string | null;
  };
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  finished_at?: string | null;
}

export interface PptProject {
  id: string;
  notebook_id?: string | null;
  session_id?: string | null;
  creation_type: "idea" | "outline" | "descriptions";
  idea_prompt?: string | null;
  outline_text?: string | null;
  description_text?: string | null;
  source_content?: string | null;
  template_style?: string | null;
  template_image_path?: string | null;
  reference_style_prompt?: string | null;
  image_aspect_ratio: "16:9" | "4:3";
  language: string;
  reference_sources: Array<Record<string, unknown>>;
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
  style_templates: Array<{ id: string; name: string; prompt: string }>;
  polling_hint_ms: number;
  creation_modes: PptCreationMode[];
}

export interface PptReferenceImageUploadResponse {
  image_path: string;
  image_url: string;
  image_name: string;
  derived_style_prompt: string;
  content_type?: string;
}

export enum AppState {
  IDLE = "IDLE",
  GENERATING_OUTLINE = "GENERATING_OUTLINE",
  GENERATING_IMAGES = "GENERATING_IMAGES",
  REVIEWING = "REVIEWING",
  EXPORTING = "EXPORTING",
}
