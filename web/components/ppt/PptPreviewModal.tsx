"use client";

import React, { useMemo, useState } from "react";
import {
  AlertCircle,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";

import { apiUrl } from "@/lib/api";
import {
  PresentationOutline,
  PptSlideChatMessage,
  SlideContent,
} from "@/types/ppt";

interface ImageProgress {
  current: number;
  total: number;
}

interface PptPreviewModalProps {
  isOpen: boolean;
  outline: PresentationOutline | null;
  isExporting: boolean;
  isProjectGenerating?: boolean;
  imageProgress?: ImageProgress;
  warnings?: string[];
  generatingSlideIndices?: number[];
  selectedSlideId?: string;
  chatMessages?: PptSlideChatMessage[];
  isChatLoading?: boolean;
  isChatSubmitting?: boolean;
  onClose: () => void;
  onExport: () => void;
  onRegenerateSlide?: (index: number, slide: SlideContent) => void;
  onSelectSlide?: (slideId: string) => void;
  onSubmitSlideChat?: (message: string) => Promise<void> | void;
}

const getSlideSelectionId = (slide: SlideContent, index: number) =>
  slide.pageId || `slide-${index}`;

const GENERATING_STATUSES = new Set([
  "DESCRIPTION_QUEUED",
  "DESCRIPTION_GENERATING",
  "IMAGE_QUEUED",
  "IMAGE_GENERATING",
]);

export default function PptPreviewModal({
  isOpen,
  outline,
  isExporting,
  isProjectGenerating = false,
  imageProgress,
  warnings = [],
  generatingSlideIndices = [],
  selectedSlideId,
  chatMessages = [],
  isChatLoading = false,
  isChatSubmitting = false,
  onClose,
  onExport,
  onRegenerateSlide,
  onSelectSlide,
  onSubmitSlideChat,
}: PptPreviewModalProps) {
  const [chatDraft, setChatDraft] = useState<{ slideId: string; text: string }>(
    {
      slideId: "",
      text: "",
    },
  );

  const selectedSlideEntry = useMemo(() => {
    if (!outline) return null;
    const selectedIndex = outline.slides.findIndex(
      (slide, index) => getSlideSelectionId(slide, index) === selectedSlideId,
    );
    const nextIndex = selectedIndex >= 0 ? selectedIndex : 0;
    const slide = outline.slides[nextIndex];
    if (!slide) return null;
    return { index: nextIndex, slide };
  }, [outline, selectedSlideId]);
  const selectedSlide = selectedSlideEntry?.slide ?? null;

  const canExport = useMemo(() => {
    if (!outline || outline.slides.length === 0 || isExporting) return false;
    return !outline.slides.some(
      (slide, index) =>
        slide.isDirty ||
        slide.status === "FAILED" ||
        GENERATING_STATUSES.has(slide.status || "") ||
        !outline.slides[index]?.generatedImageUrl,
    );
  }, [outline, isExporting]);

  if (!isOpen) return null;

  const activeSlideId = selectedSlide?.pageId || "";
  const activeChatInput =
    activeSlideId && chatDraft.slideId === activeSlideId ? chatDraft.text : "";

  const getSlideImageSrc = (slide: SlideContent) =>
    slide.generatedImageUrl ? apiUrl(slide.generatedImageUrl) : "";

  const isSlideGenerating = (slide: SlideContent, index: number) =>
    generatingSlideIndices.includes(index) ||
    GENERATING_STATUSES.has(slide.status || "");

  const renderStatusBadge = (slide: SlideContent, index: number) => {
    if (isSlideGenerating(slide, index)) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-1 text-[10px] font-medium text-sky-700">
          <Loader2 className="h-3 w-3 animate-spin" />
          生成中
        </span>
      );
    }
    if (slide.status === "FAILED") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-1 text-[10px] font-medium text-red-700">
          <AlertCircle className="h-3 w-3" />
          失败
        </span>
      );
    }
    if (slide.isDirty) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 text-[10px] font-medium text-amber-700">
          待重生成
        </span>
      );
    }
    if (slide.generatedImageUrl) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-medium text-emerald-700">
          就绪
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-600">
        未生成
      </span>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative w-full max-w-7xl h-[90vh] bg-white rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            <div className="text-sm font-semibold text-slate-700">PPT 预览</div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onExport}
              disabled={!canExport}
              className="px-4 py-2 text-sm rounded-lg bg-slate-900 text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
            >
              {isExporting ? "导出中..." : "导出 PPT"}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <X className="w-4 h-4 text-slate-500" />
            </button>
          </div>
        </div>

        {outline ? (
          <div className="flex-1 overflow-hidden flex flex-col xl:flex-row">
            <aside className="w-full xl:w-72 border-b xl:border-b-0 xl:border-r border-slate-100 bg-slate-50/70 flex flex-col">
              <div className="px-4 py-4 border-b border-slate-100 bg-white/80">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  页面缩略图
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  这里显示的是将被导出的真实页面图。
                </div>
              </div>
              <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
                {outline.slides.map((slide, index) => {
                  const slideSelectionId = getSlideSelectionId(slide, index);
                  const selected = selectedSlideEntry?.index === index;
                  const imageSrc = getSlideImageSrc(slide);
                  const generating = isSlideGenerating(slide, index);
                  return (
                    <button
                      key={slideSelectionId}
                      type="button"
                      onClick={() => onSelectSlide?.(slideSelectionId)}
                      className={`w-full rounded-xl border text-left transition ${
                        selected
                          ? "border-slate-900 bg-white shadow-sm"
                          : "border-slate-200 bg-white/80 hover:border-slate-300"
                      }`}
                    >
                      <div className="relative aspect-[16/9] overflow-hidden rounded-t-xl bg-slate-100">
                        {imageSrc ? (
                          <img
                            src={imageSrc}
                            alt={slide.title || `Slide ${index + 1}`}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center text-slate-400">
                            <ImageIcon className="h-6 w-6 mb-2" />
                            <span className="text-xs">暂无页图</span>
                          </div>
                        )}
                        {generating && (
                          <div className="absolute inset-0 bg-slate-900/35 backdrop-blur-[1px] flex items-center justify-center">
                            <span className="inline-flex items-center gap-2 rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-slate-700">
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              生成中
                            </span>
                          </div>
                        )}
                        {!generating && slide.isDirty && (
                          <div className="absolute inset-0 bg-amber-900/10 flex items-start justify-end p-2">
                            <span className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-medium text-amber-700">
                              待重生成
                            </span>
                          </div>
                        )}
                      </div>
                      <div className="px-3 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-xs text-slate-400 mb-1">
                              第 {index + 1} 页
                            </div>
                            <div className="text-sm font-semibold text-slate-800 truncate">
                              {slide.title || "未命名页面"}
                            </div>
                          </div>
                          {renderStatusBadge(slide, index)}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </aside>

            <div className="flex-1 min-w-0 overflow-hidden flex flex-col bg-slate-50/40">
              <div className="px-6 pt-4 pb-2 flex items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: outline.themeColor }}
                    />
                    <span
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: outline.accentColor }}
                    />
                    <span className="text-xs text-slate-400 uppercase tracking-wider">
                      Theme
                    </span>
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">
                    {outline.title}
                  </h3>
                  {outline.subtitle && (
                    <p className="text-sm text-slate-500">{outline.subtitle}</p>
                  )}
                </div>

                {imageProgress && imageProgress.total > 0 && (
                  <div className="text-xs text-slate-500">
                    图片生成{" "}
                    {Math.min(imageProgress.current, imageProgress.total)}/
                    {imageProgress.total}
                  </div>
                )}
              </div>

              {warnings.length > 0 && (
                <div className="px-6 pb-2">
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    {warnings.slice(0, 3).map((warning, index) => (
                      <div key={`${warning}-${index}`}>{warning}</div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex-1 min-h-0 p-6 pt-4">
                {selectedSlideEntry && selectedSlide ? (
                  <div className="h-full rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
                    <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <div className="text-[11px] uppercase tracking-wide text-slate-400">
                          当前页
                        </div>
                        <div className="text-sm font-semibold text-slate-900 truncate">
                          第 {selectedSlideEntry.index + 1} 页 ·{" "}
                          {selectedSlide.title || "未命名页面"}
                        </div>
                      </div>
                      <div className="shrink-0">
                        {renderStatusBadge(
                          selectedSlide,
                          selectedSlideEntry.index,
                        )}
                      </div>
                    </div>

                    <div className="flex-1 min-h-0 bg-slate-100/80 p-4 md:p-6">
                      <div className="relative h-full w-full rounded-xl overflow-hidden bg-slate-900/5 flex items-center justify-center">
                        {getSlideImageSrc(selectedSlide) ? (
                          <img
                            src={getSlideImageSrc(selectedSlide)}
                            alt={selectedSlide.title || "当前页预览"}
                            className="max-w-full max-h-full object-contain"
                          />
                        ) : (
                          <div className="text-center text-slate-400 px-6">
                            <ImageIcon className="h-10 w-10 mx-auto mb-3" />
                            <div className="text-sm font-medium">
                              当前页还没有可预览的页图
                            </div>
                            <div className="mt-1 text-xs">
                              生成完成后，这里会显示最终导出的真实页面。
                            </div>
                          </div>
                        )}

                        {isSlideGenerating(
                          selectedSlide,
                          selectedSlideEntry.index,
                        ) && (
                          <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-[1px] flex items-center justify-center">
                            <div className="rounded-2xl bg-white/90 px-4 py-3 text-sm font-medium text-slate-700 inline-flex items-center gap-2 shadow-sm">
                              <Loader2 className="h-4 w-4 animate-spin" />
                              正在生成当前页
                            </div>
                          </div>
                        )}

                        {!isSlideGenerating(
                          selectedSlide,
                          selectedSlideEntry.index,
                        ) &&
                          selectedSlide.isDirty && (
                            <div className="absolute inset-0 bg-amber-900/10 flex items-start justify-end p-4">
                              <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">
                                当前显示的是上一次已生成结果
                              </span>
                            </div>
                          )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-full rounded-2xl border border-dashed border-slate-200 bg-white/80 flex items-center justify-center text-slate-500 text-sm">
                    暂无可预览页面
                  </div>
                )}
              </div>
            </div>

            <aside className="w-full xl:w-96 border-t xl:border-t-0 xl:border-l border-slate-100 bg-slate-50/60 flex flex-col">
              <div className="px-5 py-4 border-b border-slate-100 bg-white/80">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  单页编辑
                </div>
                {selectedSlide ? (
                  <>
                    <div className="mt-1 text-sm font-semibold text-slate-900">
                      {selectedSlide.title || "未命名页面"}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      通过自然语言描述希望修改的内容，系统会自动分类并重生成当前页的真实页面图。
                    </div>
                  </>
                ) : (
                  <div className="mt-1 text-xs text-slate-500">
                    请选择左侧页面进行编辑。
                  </div>
                )}

                {selectedSlideEntry?.slide.pageId && onRegenerateSlide && (
                  <button
                    type="button"
                    disabled={
                      isProjectGenerating ||
                      isSlideGenerating(
                        selectedSlideEntry.slide,
                        selectedSlideEntry.index,
                      )
                    }
                    onClick={() =>
                      onRegenerateSlide(
                        selectedSlideEntry.index,
                        selectedSlideEntry.slide,
                      )
                    }
                    className="mt-3 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    重新生成当前页
                  </button>
                )}
                {isProjectGenerating && (
                  <div className="mt-2 text-[11px] text-slate-400">
                    当前整份 PPT 仍在生成中，单页重生成和编辑暂不可用。
                  </div>
                )}
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3">
                {isChatLoading ? (
                  <div className="text-sm text-slate-500">
                    正在加载编辑历史...
                  </div>
                ) : chatMessages.length > 0 ? (
                  chatMessages.map((message) => (
                    <div
                      key={message.id}
                      className={`rounded-xl px-3 py-2 text-sm leading-6 shadow-sm ${
                        message.role === "user"
                          ? "ml-6 bg-slate-900 text-white"
                          : "mr-6 bg-white text-slate-700 border border-slate-200"
                      }`}
                    >
                      {message.content}
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-slate-500">
                    当前页还没有编辑历史。
                  </div>
                )}
              </div>

              <div className="border-t border-slate-100 bg-white px-5 py-4">
                <textarea
                  value={activeChatInput}
                  onChange={(event) => {
                    setChatDraft({
                      slideId: activeSlideId,
                      text: event.target.value,
                    });
                  }}
                  placeholder="例如：把这一页改成更像结论页，标题更短，图片更克制。"
                  rows={4}
                  disabled={
                    !selectedSlide?.pageId ||
                    isChatSubmitting ||
                    isProjectGenerating
                  }
                  className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                />
                <div className="mt-3 flex items-center justify-between gap-3">
                  <div className="text-[11px] text-slate-400">
                    自然语言编辑会自动触发当前页重生成。
                  </div>
                  <button
                    type="button"
                    disabled={
                      !selectedSlide?.pageId ||
                      !activeChatInput.trim() ||
                      isChatSubmitting ||
                      isProjectGenerating
                    }
                    onClick={async () => {
                      if (!activeChatInput.trim() || !onSubmitSlideChat) return;
                      const nextInput = activeChatInput.trim();
                      await onSubmitSlideChat(nextInput);
                      setChatDraft({ slideId: activeSlideId, text: "" });
                    }}
                    className="shrink-0 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isChatSubmitting ? "处理中..." : "发送修改"}
                  </button>
                </div>
              </div>
            </aside>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
            正在生成大纲...
          </div>
        )}
      </div>
    </div>
  );
}
