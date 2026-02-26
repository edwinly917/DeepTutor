"use client";

import { useState, useEffect, useRef } from "react";
import {
  Lightbulb,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Loader2,
  Check,
  Save,
  Sparkles,
  Brain,
  Zap,
  FileText,
  FileQuestion,
  BrainCircuit,
  PanelLeftOpen,
  X,
  ShieldAlert,
  Link2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { apiUrl, wsUrl } from "@/lib/api";
import { processLatexContent } from "@/lib/latex";
import AddToNotebookModal from "@/components/AddToNotebookModal";
import { useGlobal } from "@/context/GlobalContext";

interface Notebook {
  id: string;
  name: string;
  description: string;
  record_count: number;
  color: string;
}

interface NotebookRecord {
  id: string;
  title: string;
  user_query: string;
  output: string;
  type: string;
}

interface ResearchIdea {
  id: string;
  knowledge_point: string;
  description: string;
  research_ideas: string[];
  statement: string;
  expanded: boolean;
  selected: boolean;
}

interface SelectedRecord extends NotebookRecord {
  notebookId: string;
  notebookName: string;
}

const statusText = {
  connecting: "连接中",
  initializing: "初始化",
  running: "生成中",
  completed: "已完成",
  error: "异常",
  stopped: "已停止",
} as const;

const getRecordTypeStyle = (type: string) => {
  switch (type) {
    case "solve":
      return {
        className:
          "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800",
        label: "解题",
        Icon: Zap,
      };
    case "question":
      return {
        className:
          "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-800",
        label: "题目",
        Icon: FileQuestion,
      };
    case "research":
      return {
        className:
          "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800",
        label: "研究",
        Icon: BrainCircuit,
      };
    case "co_writer":
      return {
        className:
          "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-800",
        label: "写作",
        Icon: FileText,
      };
    default:
      return {
        className:
          "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
        label: type || "记录",
        Icon: FileText,
      };
  }
};

export default function IdeaGenPage() {
  const { ideaGenState, setIdeaGenState } = useGlobal();

  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [expandedNotebooks, setExpandedNotebooks] = useState<Set<string>>(
    new Set(),
  );
  const [notebookRecordsMap, setNotebookRecordsMap] = useState<
    Map<string, NotebookRecord[]>
  >(new Map());
  const [selectedRecords, setSelectedRecords] = useState<
    Map<string, SelectedRecord>
  >(new Map());
  const [loadingNotebooks, setLoadingNotebooks] = useState(true);
  const [loadingRecordsFor, setLoadingRecordsFor] = useState<Set<string>>(
    new Set(),
  );

  const [userThoughts, setUserThoughts] = useState("");
  const [mobileView, setMobileView] = useState<"source" | "result">("source");
  const [sourceDrawerOpen, setSourceDrawerOpen] = useState(false);

  const isGenerating = ideaGenState.isGenerating;
  const generationStatus = ideaGenState.generationStatus;
  const generatedIdeas = ideaGenState.generatedIdeas;
  const progress = ideaGenState.progress;

  const setIsGenerating = (val: boolean) =>
    setIdeaGenState((prev) => ({ ...prev, isGenerating: val }));
  const setGenerationStatus = (val: string) =>
    setIdeaGenState((prev) => ({ ...prev, generationStatus: val }));
  const setGeneratedIdeas = (
    updater: ResearchIdea[] | ((prev: ResearchIdea[]) => ResearchIdea[]),
  ) => {
    setIdeaGenState((prev) => ({
      ...prev,
      generatedIdeas:
        typeof updater === "function" ? updater(prev.generatedIdeas) : updater,
    }));
  };
  const setProgress = (val: { current: number; total: number } | null) =>
    setIdeaGenState((prev) => ({ ...prev, progress: val }));

  const [showSaveModal, setShowSaveModal] = useState(false);
  const [ideaToSave, setIdeaToSave] = useState<ResearchIdea | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchNotebooks();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const fetchNotebooks = async () => {
    try {
      const res = await fetch(apiUrl("/api/v1/notebook/list"));
      const data = await res.json();
      const notebooksWithRecords = (data.notebooks || []).filter(
        (nb: Notebook) => nb.record_count > 0,
      );
      setNotebooks(notebooksWithRecords);
      setLoadingNotebooks(false);
    } catch (err) {
      console.error("Failed to fetch notebooks:", err);
      setLoadingNotebooks(false);
    }
  };

  const fetchNotebookRecords = async (notebookId: string) => {
    if (notebookRecordsMap.has(notebookId)) return;

    setLoadingRecordsFor((prev) => new Set([...prev, notebookId]));
    try {
      const res = await fetch(apiUrl(`/api/v1/notebook/${notebookId}`));
      const data = await res.json();
      setNotebookRecordsMap((prev) =>
        new Map(prev).set(notebookId, data.records || []),
      );
    } catch (err) {
      console.error("Failed to fetch notebook records:", err);
    } finally {
      setLoadingRecordsFor((prev) => {
        const newSet = new Set(prev);
        newSet.delete(notebookId);
        return newSet;
      });
    }
  };

  const toggleNotebookExpanded = (notebookId: string) => {
    const notebook = notebooks.find((nb) => nb.id === notebookId);
    if (!notebook) return;

    setExpandedNotebooks((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(notebookId)) {
        newSet.delete(notebookId);
      } else {
        newSet.add(notebookId);
        fetchNotebookRecords(notebookId);
      }
      return newSet;
    });
  };

  const toggleRecordSelection = (
    record: NotebookRecord,
    notebookId: string,
    notebookName: string,
  ) => {
    setSelectedRecords((prev) => {
      const newMap = new Map(prev);
      if (newMap.has(record.id)) {
        newMap.delete(record.id);
      } else {
        newMap.set(record.id, { ...record, notebookId, notebookName });
      }
      return newMap;
    });
  };

  const selectAllFromNotebook = (notebookId: string, notebookName: string) => {
    const records = notebookRecordsMap.get(notebookId) || [];
    setSelectedRecords((prev) => {
      const newMap = new Map(prev);
      records.forEach((r) =>
        newMap.set(r.id, { ...r, notebookId, notebookName }),
      );
      return newMap;
    });
  };

  const deselectAllFromNotebook = (notebookId: string) => {
    const records = notebookRecordsMap.get(notebookId) || [];
    const recordIds = new Set(records.map((r) => r.id));
    setSelectedRecords((prev) => {
      const newMap = new Map(prev);
      recordIds.forEach((id) => newMap.delete(id));
      return newMap;
    });
  };

  const clearAllSelections = () => {
    setSelectedRecords(new Map());
  };

  const canGenerate =
    selectedRecords.size > 0 || userThoughts.trim().length > 0;

  const stopGeneration = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsGenerating(false);
    setGenerationStatus("Generation stopped");
  };

  const startGeneration = () => {
    if (!canGenerate) return;

    if (wsRef.current) {
      wsRef.current.close();
    }

    setMobileView("result");
    setSourceDrawerOpen(false);
    setIsGenerating(true);
    setGenerationStatus("Connecting...");
    setGeneratedIdeas([]);
    setProgress(null);

    const ws = new WebSocket(wsUrl("/api/v1/ideagen/generate"));
    wsRef.current = ws;

    ws.onopen = () => {
      setGenerationStatus("Initializing...");
      const recordsArray = Array.from(selectedRecords.values()).map((r) => ({
        id: r.id,
        title: r.title,
        user_query: r.user_query,
        output: r.output,
        type: r.type,
      }));
      ws.send(
        JSON.stringify({
          records: recordsArray.length > 0 ? recordsArray : undefined,
          user_thoughts: userThoughts.trim() || undefined,
        }),
      );
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "status":
          setGenerationStatus(data.message);
          if (data.stage === "complete") {
            setIsGenerating(false);
          }
          if (data.data?.index && data.data?.total) {
            setProgress({ current: data.data.index, total: data.data.total });
          }
          break;
        case "progress":
          if (data.data?.index && data.data?.total) {
            setProgress({ current: data.data.index, total: data.data.total });
          }
          break;
        case "idea":
          setGeneratedIdeas((prev) => [
            ...prev,
            { ...data.data, selected: false },
          ]);
          break;
        case "complete":
          setGenerationStatus("Completed!");
          setIsGenerating(false);
          break;
        case "error":
          setGenerationStatus(
            `Error: ${data.message || data.content || "Unknown error"}`,
          );
          setIsGenerating(false);
          break;
      }
    };

    ws.onerror = () => {
      setGenerationStatus("Connection Error");
      setIsGenerating(false);
    };

    ws.onclose = () => {
      wsRef.current = null;
    };
  };

  const toggleIdeaExpanded = (ideaId: string) => {
    setGeneratedIdeas((prev) =>
      prev.map((idea) =>
        idea.id === ideaId ? { ...idea, expanded: !idea.expanded } : idea,
      ),
    );
  };

  const toggleIdeaSelected = (ideaId: string) => {
    setGeneratedIdeas((prev) =>
      prev.map((idea) =>
        idea.id === ideaId ? { ...idea, selected: !idea.selected } : idea,
      ),
    );
  };

  const selectAllIdeas = () => {
    setGeneratedIdeas((prev) =>
      prev.map((idea) => ({ ...idea, selected: true })),
    );
  };

  const deselectAllIdeas = () => {
    setGeneratedIdeas((prev) =>
      prev.map((idea) => ({ ...idea, selected: false })),
    );
  };

  const saveIdea = (idea: ResearchIdea) => {
    setIdeaToSave(idea);
    setShowSaveModal(true);
  };

  const saveSelectedIdeas = () => {
    const selected = generatedIdeas.filter((i) => i.selected);
    if (selected.length > 0) {
      const combinedIdea: ResearchIdea = {
        id: "combined",
        knowledge_point: "Collection of Research Ideas",
        description: `Research ideas containing ${selected.length} knowledge points`,
        research_ideas: selected.flatMap((i) => i.research_ideas),
        statement: selected.map((i) => i.statement).join("\n\n---\n\n"),
        expanded: false,
        selected: false,
      };
      setIdeaToSave(combinedIdea);
      setShowSaveModal(true);
    }
  };

  const selectedIdeasCount = generatedIdeas.filter((i) => i.selected).length;

  const lowerStatus = generationStatus.toLowerCase();
  const isErrorStatus =
    lowerStatus.includes("error") || lowerStatus.includes("connection");
  const isStoppedStatus = lowerStatus.includes("stopped");
  const isCompletedStatus = lowerStatus.includes("completed");

  const normalizedStatusLabel = isGenerating
    ? statusText.running
    : isErrorStatus
      ? statusText.error
      : isStoppedStatus
        ? statusText.stopped
        : isCompletedStatus
          ? statusText.completed
          : statusText.connecting;

  const renderSourcePanel = ({
    drawerMode = false,
  }: {
    drawerMode?: boolean;
  }) => (
    <div className="h-full flex flex-col bg-white dark:bg-slate-900 min-h-0">
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/60 shrink-0 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <BookOpen className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">
            来源选择
          </h2>
          {selectedRecords.size > 0 && (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
              已选 {selectedRecords.size}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {selectedRecords.size > 0 && (
            <button
              onClick={clearAllSelections}
              className="text-xs text-slate-500 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400"
            >
              清空
            </button>
          )}
          {drawerMode && (
            <button
              onClick={() => setSourceDrawerOpen(false)}
              className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Close source panel"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {loadingNotebooks ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 animate-spin text-blue-600 dark:text-blue-400" />
          </div>
        ) : notebooks.length === 0 ? (
          <div className="py-10 px-4 text-center text-sm text-slate-500 dark:text-slate-400">
            当前没有可用的笔记本记录
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {notebooks.map((notebook) => {
              const isExpanded = expandedNotebooks.has(notebook.id);
              const records = notebookRecordsMap.get(notebook.id) || [];
              const isLoading = loadingRecordsFor.has(notebook.id);
              const selectedFromThis = records.filter((r) =>
                selectedRecords.has(r.id),
              ).length;

              return (
                <div key={notebook.id}>
                  <button
                    className="w-full px-4 py-3 flex items-center gap-2 hover:bg-slate-50 dark:hover:bg-slate-800/70 transition-colors"
                    onClick={() => toggleNotebookExpanded(notebook.id)}
                  >
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: notebook.color || "#94a3b8" }}
                    />
                    <span className="flex-1 text-left text-sm text-slate-700 dark:text-slate-200 truncate">
                      {notebook.name}
                    </span>
                    <span className="text-xs text-slate-400 dark:text-slate-500">
                      {selectedFromThis > 0 && (
                        <span className="text-blue-600 dark:text-blue-400 font-medium">
                          {selectedFromThis}/
                        </span>
                      )}
                      {notebook.record_count}
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="px-4 pb-3 pl-10 bg-slate-50/50 dark:bg-slate-900/30">
                      {isLoading ? (
                        <div className="flex items-center justify-center py-4">
                          <Loader2 className="w-4 h-4 animate-spin text-blue-600 dark:text-blue-400" />
                        </div>
                      ) : records.length === 0 ? (
                        <div className="py-3 text-xs text-slate-400 dark:text-slate-500 text-center">
                          暂无记录
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-3 mb-2">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                selectAllFromNotebook(
                                  notebook.id,
                                  notebook.name,
                                );
                              }}
                              className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                            >
                              全选
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                deselectAllFromNotebook(notebook.id);
                              }}
                              className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            >
                              取消选择
                            </button>
                          </div>
                          <div className="space-y-1.5">
                            {records.map((record) => {
                              const selected = selectedRecords.has(record.id);
                              const typeStyle = getRecordTypeStyle(record.type);
                              return (
                                <div
                                  key={record.id}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleRecordSelection(
                                      record,
                                      notebook.id,
                                      notebook.name,
                                    );
                                  }}
                                  className={`p-2 rounded-lg border cursor-pointer transition-all ${
                                    selected
                                      ? "bg-blue-50 border-blue-200 dark:bg-blue-950/30 dark:border-blue-800"
                                      : "bg-white/80 border-transparent hover:border-slate-200 dark:bg-slate-800/60 dark:hover:border-slate-700"
                                  }`}
                                >
                                  <div className="flex items-center gap-2 min-w-0">
                                    <div
                                      className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                                        selected
                                          ? "bg-blue-600 border-blue-600 text-white"
                                          : "border-slate-300 dark:border-slate-600"
                                      }`}
                                    >
                                      {selected && (
                                        <Check className="w-2.5 h-2.5" />
                                      )}
                                    </div>
                                    <span
                                      className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border ${typeStyle.className}`}
                                    >
                                      <typeStyle.Icon className="w-2.5 h-2.5" />
                                      {typeStyle.label}
                                    </span>
                                    <span className="text-xs text-slate-700 dark:text-slate-200 truncate">
                                      {record.title}
                                    </span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/70 shrink-0">
        <label className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide block mb-2">
          创意指令 {selectedRecords.size > 0 ? "（可选）" : "（必填）"}
        </label>
        <textarea
          value={userThoughts}
          onChange={(e) => setUserThoughts(e.target.value)}
          placeholder={
            selectedRecords.size > 0
              ? "补充你的研究目标、约束条件或期望输出形式..."
              : "描述你的研究主题或灵感方向..."
          }
          className="w-full px-3 py-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 resize-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
          rows={4}
        />
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 flex items-start gap-1.5">
          <Link2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          支持仅文本生成，也支持“笔记记录 + 文本补充”的混合生成。
        </p>
      </div>

      <div className="p-4 border-t border-slate-100 dark:border-slate-800 shrink-0 bg-white dark:bg-slate-900 space-y-2">
        <button
          onClick={startGeneration}
          disabled={isGenerating || !canGenerate}
          className="w-full px-4 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-sm font-medium shadow-md shadow-blue-500/20"
        >
          {isGenerating ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              {statusText.running}
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              {selectedRecords.size > 0
                ? `生成创意（${selectedRecords.size} 条来源）`
                : "生成创意"}
            </>
          )}
        </button>
        {isGenerating && (
          <button
            onClick={stopGeneration}
            className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-sm"
          >
            停止生成
          </button>
        )}
      </div>
    </div>
  );

  const renderResultPanel = () => (
    <div className="h-full flex flex-col bg-white dark:bg-slate-900 min-h-0">
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/60 shrink-0 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-300 flex items-center justify-center">
            <Lightbulb className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
              创意结果
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
              可勾选、展开与批量保存
            </p>
          </div>
        </div>

        {generatedIdeas.length > 0 && (
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={selectAllIdeas}
              className="px-2.5 py-1.5 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40 rounded-lg transition-colors"
            >
              全选
            </button>
            <button
              onClick={deselectAllIdeas}
              className="px-2.5 py-1.5 text-xs text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
            >
              清选
            </button>
            <button
              onClick={saveSelectedIdeas}
              disabled={selectedIdeasCount === 0}
              className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center gap-1"
            >
              <Save className="w-3 h-3" />
              保存所选
            </button>
          </div>
        )}
      </div>

      {(isGenerating || generationStatus) && (
        <div
          className={`px-4 py-2.5 border-b flex items-center justify-between gap-3 ${
            isErrorStatus
              ? "bg-red-50 border-red-100 dark:bg-red-950/30 dark:border-red-900"
              : isCompletedStatus
                ? "bg-emerald-50 border-emerald-100 dark:bg-emerald-950/30 dark:border-emerald-900"
                : isStoppedStatus
                  ? "bg-amber-50 border-amber-100 dark:bg-amber-950/30 dark:border-amber-900"
                  : "bg-blue-50 border-blue-100 dark:bg-blue-950/30 dark:border-blue-900"
          }`}
        >
          <div className="flex items-center gap-2 min-w-0">
            {isGenerating ? (
              <Loader2 className="w-4 h-4 animate-spin text-blue-600 dark:text-blue-300" />
            ) : isErrorStatus ? (
              <ShieldAlert className="w-4 h-4 text-red-600 dark:text-red-300" />
            ) : (
              <Sparkles className="w-4 h-4 text-slate-600 dark:text-slate-300" />
            )}
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {normalizedStatusLabel}
            </span>
            <span className="text-sm text-slate-700 dark:text-slate-200 truncate">
              {generationStatus}
            </span>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {progress && (
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {progress.current} / {progress.total}
              </span>
            )}
            {isErrorStatus && !isGenerating && (
              <button
                onClick={startGeneration}
                disabled={!canGenerate}
                className="px-2.5 py-1 text-xs rounded-lg border border-red-200 text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-900/50"
              >
                重试
              </button>
            )}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 lg:p-5 bg-slate-50/30 dark:bg-slate-900/20 min-h-0">
        {generatedIdeas.length === 0 && !isGenerating ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 flex items-center justify-center mb-4">
              <Brain className="w-7 h-7" />
            </div>
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-2">
              暂无创意结果
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md">
              先选择来源记录或填写创意指令，再开始生成。支持从多笔记本聚合上下文。
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {generatedIdeas.map((idea) => (
              <div
                key={idea.id}
                className={`rounded-2xl border transition-all ${
                  idea.selected
                    ? "bg-blue-50 border-blue-200 shadow-sm dark:bg-blue-950/20 dark:border-blue-800"
                    : "bg-white border-slate-200 hover:border-slate-300 dark:bg-slate-800/70 dark:border-slate-700 dark:hover:border-slate-600"
                }`}
              >
                <div className="p-4 flex items-start gap-3">
                  <button
                    onClick={() => toggleIdeaSelected(idea.id)}
                    className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 transition-all ${
                      idea.selected
                        ? "bg-blue-600 border-blue-600 text-white"
                        : "border-slate-300 dark:border-slate-600 hover:border-blue-400"
                    }`}
                  >
                    {idea.selected && <Check className="w-4 h-4" />}
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2 truncate">
                          <Zap className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
                          <span className="truncate">
                            {idea.knowledge_point}
                          </span>
                        </h3>
                        <p className="text-sm text-slate-600 dark:text-slate-300 mt-1 line-clamp-2">
                          {idea.description}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded-full">
                          {idea.research_ideas.length} 个想法
                        </span>
                        <button
                          onClick={() => saveIdea(idea)}
                          className="p-1.5 text-slate-400 dark:text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40 rounded-lg transition-colors"
                          title="保存到笔记本"
                        >
                          <Save className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 mt-3">
                      {idea.research_ideas.slice(0, 3).map((ri, idx) => (
                        <span
                          key={idx}
                          className="text-xs bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 px-2 py-1 rounded-lg line-clamp-1 max-w-[220px]"
                          title={ri}
                        >
                          {ri.substring(0, 64)}...
                        </span>
                      ))}
                      {idea.research_ideas.length > 3 && (
                        <span className="text-xs text-slate-500 dark:text-slate-400 self-center">
                          +{idea.research_ideas.length - 3} 条
                        </span>
                      )}
                    </div>
                  </div>

                  <button
                    onClick={() => toggleIdeaExpanded(idea.id)}
                    className="p-1.5 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                  >
                    {idea.expanded ? (
                      <ChevronDown className="w-5 h-5" />
                    ) : (
                      <ChevronRight className="w-5 h-5" />
                    )}
                  </button>
                </div>

                {idea.expanded && (
                  <div className="px-4 pb-4 pt-0 border-t border-slate-100 dark:border-slate-700">
                    <div className="mt-4 prose prose-sm prose-slate dark:prose-invert max-w-none">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                      >
                        {processLatexContent(idea.statement)}
                      </ReactMarkdown>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="h-screen flex flex-col gap-0 animate-fade-in overflow-hidden p-8 pb-0">
      <div className="mb-6 shrink-0">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100 tracking-tight flex items-center gap-3 mb-2">
          <Lightbulb className="w-8 h-8 text-purple-600 dark:text-purple-400" />
          创意生成
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
          结合多来源笔记与补充思路，生成可筛选、可保存的研究创意。
        </p>
      </div>

      <div className="flex-1 min-h-0 bg-white dark:bg-slate-900 rounded-t-2xl shadow-sm border border-slate-200 dark:border-slate-800 overflow-hidden">
        <div className="xl:hidden px-4 pt-4 pb-3 border-b border-slate-100 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-900/60">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMobileView("source")}
              className={`lg:hidden flex-1 px-3 py-2 text-sm rounded-lg border transition-colors ${
                mobileView === "source"
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700"
              }`}
            >
              来源与输入
            </button>
            <button
              onClick={() => setMobileView("result")}
              className={`lg:hidden flex-1 px-3 py-2 text-sm rounded-lg border transition-colors ${
                mobileView === "result"
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700"
              }`}
            >
              创意结果
            </button>

            <button
              onClick={() => setSourceDrawerOpen(true)}
              className="hidden lg:inline-flex xl:hidden items-center gap-2 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <PanelLeftOpen className="w-4 h-4" />
              来源与输入
            </button>

            <div className="hidden lg:flex xl:hidden items-center gap-2 text-xs text-slate-500 dark:text-slate-400 ml-auto">
              <BookOpen className="w-3.5 h-3.5" />
              已选 {selectedRecords.size} 条来源
            </div>
          </div>
        </div>

        <div className="h-full min-h-0">
          <div className="hidden xl:flex h-full min-h-0">
            <div className="w-[34%] min-w-[360px] max-w-[520px] border-r border-slate-200 dark:border-slate-800 min-h-0">
              {renderSourcePanel({ drawerMode: false })}
            </div>
            <div className="flex-1 min-w-0 min-h-0">{renderResultPanel()}</div>
          </div>

          <div className="hidden lg:flex xl:hidden h-full min-h-0 relative">
            <div className="flex-1 min-w-0 min-h-0">{renderResultPanel()}</div>

            {sourceDrawerOpen && (
              <>
                <div
                  className="absolute inset-0 bg-slate-950/30 z-20"
                  onClick={() => setSourceDrawerOpen(false)}
                />
                <div className="absolute inset-y-0 left-0 w-[420px] max-w-[92%] bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-30 shadow-2xl">
                  {renderSourcePanel({ drawerMode: true })}
                </div>
              </>
            )}
          </div>

          <div className="flex lg:hidden h-full min-h-0">
            {mobileView === "source"
              ? renderSourcePanel({})
              : renderResultPanel()}
          </div>
        </div>
      </div>

      {ideaToSave && (
        <AddToNotebookModal
          isOpen={showSaveModal}
          onClose={() => {
            setShowSaveModal(false);
            setIdeaToSave(null);
          }}
          recordType="research"
          title={`Research Idea: ${ideaToSave.knowledge_point}`}
          userQuery={ideaToSave.description}
          output={ideaToSave.statement}
          metadata={{
            ideas_count: ideaToSave.research_ideas.length,
            source: "ideagen",
          }}
        />
      )}
    </div>
  );
}
