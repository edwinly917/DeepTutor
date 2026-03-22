"use client";

import React, { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";

import SlidePreview from "@/components/ppt/SlidePreview";
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
  imageProgress?: ImageProgress;
  warnings?: string[];
  generatingSlideIndices?: number[];
  selectedSlideId?: string;
  chatMessages?: PptSlideChatMessage[];
  isChatLoading?: boolean;
  isChatSubmitting?: boolean;
  onClose: () => void;
  onExport: () => void;
  onUpdateSlide: (index: number, updatedSlide: SlideContent) => void;
  onRegenerateSlide?: (index: number, slide: SlideContent) => void;
  onSelectSlide?: (slideId: string) => void;
  onSubmitSlideChat?: (message: string) => Promise<void> | void;
}

const getSlideSelectionId = (slide: SlideContent, index: number) =>
  slide.pageId || `slide-${index}`;

export default function PptPreviewModal({
  isOpen,
  outline,
  isExporting,
  imageProgress,
  warnings = [],
  generatingSlideIndices = [],
  selectedSlideId,
  chatMessages = [],
  isChatLoading = false,
  isChatSubmitting = false,
  onClose,
  onExport,
  onUpdateSlide,
  onRegenerateSlide,
  onSelectSlide,
  onSubmitSlideChat,
}: PptPreviewModalProps) {
  const [chatInput, setChatInput] = useState("");

  const selectedSlide = useMemo(() => {
    if (!outline) return null;
    return (
      outline.slides.find(
        (slide, index) => getSlideSelectionId(slide, index) === selectedSlideId,
      ) ||
      outline.slides[0] ||
      null
    );
  }, [outline, selectedSlideId]);

  useEffect(() => {
    setChatInput("");
  }, [selectedSlideId]);

  if (!isOpen) return null;

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
              disabled={
                !outline ||
                isExporting ||
                Boolean(outline.slides.some((slide) => slide.isDirty))
              }
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
            <div className="flex-1 min-w-0 overflow-hidden flex flex-col">
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

              <div className="flex-1 overflow-y-auto px-6 pb-6">
                <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">
                  {outline.slides.map((slide, index) => {
                    const slideSelectionId = getSlideSelectionId(slide, index);
                    return (
                      <SlidePreview
                        key={slideSelectionId}
                        slide={slide}
                        index={index}
                        themeColor={outline.themeColor}
                        accentColor={outline.accentColor}
                        isGenerating={generatingSlideIndices.includes(index)}
                        isSelected={slideSelectionId === selectedSlideId}
                        onSelectSlide={(slideIndex, selected) =>
                          onSelectSlide?.(
                            getSlideSelectionId(selected, slideIndex),
                          )
                        }
                        onUpdateSlide={onUpdateSlide}
                        onRegenerateSlide={onRegenerateSlide}
                      />
                    );
                  })}
                </div>
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
                      通过自然语言描述希望修改的内容，系统会自动分类并重生成当前页。
                    </div>
                  </>
                ) : (
                  <div className="mt-1 text-xs text-slate-500">
                    请选择左侧页面进行编辑。
                  </div>
                )}
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3">
                {isChatLoading ? (
                  <div className="text-sm text-slate-500">正在加载编辑历史...</div>
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
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  placeholder="例如：把这一页改成更像结论页，标题更短，图片更克制。"
                  rows={4}
                  disabled={!selectedSlide?.pageId || isChatSubmitting}
                  className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                />
                <div className="mt-3 flex items-center justify-between gap-3">
                  <div className="text-[11px] text-slate-400">
                    手动修改会先标记 dirty，自然语言编辑会自动触发当前页重生成。
                  </div>
                  <button
                    type="button"
                    disabled={
                      !selectedSlide?.pageId ||
                      !chatInput.trim() ||
                      isChatSubmitting
                    }
                    onClick={async () => {
                      if (!chatInput.trim() || !onSubmitSlideChat) return;
                      const nextInput = chatInput.trim();
                      await onSubmitSlideChat(nextInput);
                      setChatInput("");
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
