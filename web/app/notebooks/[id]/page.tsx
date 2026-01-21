"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
    ArrowLeft,
    BookOpen,
    Plus,
    FileText,
    Send,
    Loader2,
    Microscope,
    FileDown,
    Presentation,
    GitBranch,
    Database,
    User,
    Bot,
    Clock,
    Trash2,
    ChevronRight,
    ChevronLeft,
    Upload,
    AlertCircle,
    PenTool,
    Calculator,
    GraduationCap,
    Lightbulb,
    FilePlus,
    Sparkles,
    Globe,
    Zap,
    Settings,
    Check,
    X,
    Link,
    Save,
    Settings2,
    Search,
    CheckSquare,
    Square,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { processLatexContent } from "@/lib/latex";
import { apiUrl, wsUrl } from "@/lib/api";
import { Mermaid } from "@/components/Mermaid";

interface NotebookRecord {
    id: string;
    type: "solve" | "question" | "research" | "co_writer" | "chat" | "note";
    title: string;
    user_query: string;
    output: string;
    metadata: Record<string, any>;
    created_at: number;
    kb_name?: string;
}

interface Notebook {
    id: string;
    name: string;
    description: string;
    created_at: number;
    updated_at: number;
    records: NotebookRecord[];
    color: string;
    icon: string;
}

interface KnowledgeBase {
    name: string;
    is_default?: boolean;
}

interface PptStyleTemplate {
    id: string;
    name: string;
    prompt: string;
}

interface PptTemplateInfo {
    name: string;
    size: number;
    modified_at: string;
    download_url: string;
}

interface ChatMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    isStreaming?: boolean;
}

// Source types for the left panel
interface Source {
    id: string;
    type: "web" | "file" | "kb";
    title: string;
    url?: string;
    selected: boolean;
}

export default function NotebookDetailPage() {
    const params = useParams();
    const router = useRouter();
    const notebookId = params.id as string;

    // Notebook state
    const [notebook, setNotebook] = useState<Notebook | null>(null);
    const [loading, setLoading] = useState(true);
    const [selectedRecord, setSelectedRecord] = useState<NotebookRecord | null>(null);

    // Panel collapse states
    const [leftCollapsed, setLeftCollapsed] = useState(false);
    const [rightCollapsed, setRightCollapsed] = useState(false);

    // Chat state
    const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
    const [chatInput, setChatInput] = useState("");
    const [isChatting, setIsChatting] = useState(false);
    const chatContainerRef = useRef<HTMLDivElement>(null);

    // Knowledge bases
    const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
    const [selectedKb, setSelectedKb] = useState<string>("");

    // Chat switches
    const [enableRag, setEnableRag] = useState(true);
    const [researchMode, setResearchMode] = useState<"fast" | "deep">("fast");

    // Sources panel (new)
    const [sources, setSources] = useState<Source[]>([]);
    const [searchQuery, setSearchQuery] = useState("");
    const [isSearching, setIsSearching] = useState(false);

    // Deep Research config (from original research page)
    const [planMode, setPlanMode] = useState<"quick" | "medium" | "deep" | "auto">("medium");
    const [enabledTools, setEnabledTools] = useState<string[]>(["RAG"]);
    const [enableOptimization, setEnableOptimization] = useState(true);
    const [exportContentSource, setExportContentSource] = useState<"research" | "sources">("research");
    const [pptStyleMode, setPptStyleMode] = useState<"default" | "preset" | "template" | "sources">("default");
    const [pptStyleTemplates, setPptStyleTemplates] = useState<PptStyleTemplate[]>([]);
    const [selectedPptStyleId, setSelectedPptStyleId] = useState("");
    const [pptTemplates, setPptTemplates] = useState<PptTemplateInfo[]>([]);
    const [selectedPptTemplate, setSelectedPptTemplate] = useState("");
    const [pptTemplateUploading, setPptTemplateUploading] = useState(false);
    const [researchStartTime, setResearchStartTime] = useState<number | null>(null);
    const [estimatedTimeRemaining, setEstimatedTimeRemaining] = useState<string>("");
    const [pptTemplateUseLlm, setPptTemplateUseLlm] = useState(false);
    const [pptTemplatePromptSource, setPptTemplatePromptSource] = useState<"preset" | "sources">("preset");
    const [pptStylePreviewSvg, setPptStylePreviewSvg] = useState("");
    const [pptStylePreviewLoading, setPptStylePreviewLoading] = useState(false);
    const [pptStylePreviewError, setPptStylePreviewError] = useState("");

    // Add source modal
    const [showAddSourceModal, setShowAddSourceModal] = useState(false);
    const [sourceUrl, setSourceUrl] = useState("");

    // Add note modal
    const [showAddNoteModal, setShowAddNoteModal] = useState(false);
    const [noteTitle, setNoteTitle] = useState("");
    const [noteContent, setNoteContent] = useState("");

    // Studio state
    const [studioMode, setStudioMode] = useState<"idle" | "research" | "question" | "solver" | "guide" | "ideagen" | "pdf" | "ppt" | "mindmap">("idle");
    const [researchTopic, setResearchTopic] = useState("");
    const [researchRunning, setResearchRunning] = useState(false);
    const [researchReport, setResearchReport] = useState("");
    const [mindmapCode, setMindmapCode] = useState("");
    const [isExporting, setIsExporting] = useState(false);

    // Error states
    const [chatError, setChatError] = useState<string | null>(null);
    const [researchError, setResearchError] = useState<string | null>(null);

    // Deep Research progress states
    const [researchPhase, setResearchPhase] = useState<"idle" | "planning" | "researching" | "reporting">("idle");
    const [researchProgress, setResearchProgress] = useState({ current: 0, total: 0 });
    const [currentSubTopic, setCurrentSubTopic] = useState("");
    const [subTopics, setSubTopics] = useState<string[]>([]);

    // WebSocket refs
    const wsRef = useRef<WebSocket | null>(null);
    const chatWsRef = useRef<WebSocket | null>(null);
    const pptTemplateInputRef = useRef<HTMLInputElement>(null);

    const hasSelectedSources = sources.some((source) => source.selected);
    const canExport = exportContentSource === "research" ? !!researchReport : hasSelectedSources;
    const hasPptPresets = pptStyleTemplates.length > 0 && !!selectedPptStyleId;
    const needsSourceForStyle =
        pptStyleMode === "sources" ||
        (pptStyleMode === "template" && pptTemplateUseLlm && pptTemplatePromptSource === "sources");
    const canUseSourceStyle = !needsSourceForStyle || hasSelectedSources;
    const needsPresetForStyle =
        pptStyleMode === "preset" ||
        (pptStyleMode === "template" && pptTemplateUseLlm && pptTemplatePromptSource === "preset");
    const canUsePresetStyle = !needsPresetForStyle || hasPptPresets;
    const canUseTemplateStyle = pptStyleMode !== "template" || !!selectedPptTemplate;
    const canExportPpt = canExport && canUseSourceStyle && canUsePresetStyle && canUseTemplateStyle;

    // Fetch notebook
    useEffect(() => {
        fetchNotebook();
        fetchKnowledgeBases();
    }, [notebookId]);

    useEffect(() => {
        fetchPptStyleTemplates();
        fetchPptTemplates();
    }, []);

    useEffect(() => {
        setPptStylePreviewSvg("");
        setPptStylePreviewError("");
    }, [pptStyleMode, selectedPptStyleId, pptTemplatePromptSource]);

    // Auto-scroll chat
    useEffect(() => {
        if (chatContainerRef.current) {
            chatContainerRef.current.scrollTo({
                top: chatContainerRef.current.scrollHeight,
                behavior: "smooth",
            });
        }
    }, [chatMessages]);

    const fetchNotebook = async () => {
        try {
            const res = await fetch(apiUrl(`/api/v1/notebook/${notebookId}`));
            if (!res.ok) throw new Error("未找到笔记本");
            const data = await res.json();
            setNotebook(data);
        } catch (err) {
            console.error("Failed to fetch notebook:", err);
            router.push("/notebooks");
        } finally {
            setLoading(false);
        }
    };

    const fetchKnowledgeBases = async () => {
        try {
            const res = await fetch(apiUrl("/api/v1/knowledge/list"));
            const data = await res.json();
            setKbs(data || []);
            if (data.length > 0) {
                const defaultKb = data.find((kb: KnowledgeBase) => kb.is_default);
                setSelectedKb(defaultKb?.name || data[0].name);
            }
        } catch (err) {
            console.error("Failed to fetch KBs:", err);
        }
    };

    const fetchPptStyleTemplates = async () => {
        try {
            const res = await fetch(apiUrl("/api/v1/research/ppt_style_templates"));
            if (!res.ok) return;
            const data = await res.json();
            const templates = data.templates || [];
            setPptStyleTemplates(templates);
            if (!selectedPptStyleId && templates.length > 0) {
                setSelectedPptStyleId(templates[0].id);
            }
        } catch (err) {
            console.error("Failed to fetch PPT style templates:", err);
        }
    };

    const fetchPptTemplates = async () => {
        try {
            const res = await fetch(apiUrl("/api/v1/research/ppt_templates"));
            if (!res.ok) return;
            const data = await res.json();
            setPptTemplates(data.templates || []);
            if (!selectedPptTemplate && data.templates?.length > 0) {
                setSelectedPptTemplate(data.templates[0].name);
            }
        } catch (err) {
            console.error("Failed to fetch PPT templates:", err);
        }
    };

    const handleUploadPptTemplate = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setPptTemplateUploading(true);
        try {
            const formData = new FormData();
            formData.append("file", file);
            const res = await fetch(apiUrl("/api/v1/research/ppt_templates/upload"), {
                method: "POST",
                body: formData,
            });
            if (!res.ok) throw new Error("Upload failed");
            await fetchPptTemplates();
            if (pptTemplateInputRef.current) {
                pptTemplateInputRef.current.value = "";
            }
        } catch (err) {
            console.error("PPT template upload failed:", err);
        } finally {
            setPptTemplateUploading(false);
        }
    };



    // Chat function using WebSocket
    const handleSendChat = () => {
        if (!chatInput.trim() || isChatting) return;

        // If Deep Research mode is active, trigger full research flow
        if (researchMode === "deep") {
            setResearchTopic(chatInput);
            setChatInput("");
            // Add user message to chat
            setChatMessages((prev) => [
                ...prev,
                { id: Date.now().toString(), role: "user", content: chatInput },
                { id: (Date.now() + 1).toString(), role: "assistant", content: "正在启动深度研究...", isStreaming: true },
            ]);
            // Start research with the topic
            setTimeout(() => {
                startResearchWithTopic(chatInput);
            }, 100);
            return;
        }

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: "user",
            content: chatInput,
        };

        setChatMessages((prev) => [...prev, userMessage]);
        setChatInput("");
        setIsChatting(true);
        setChatError(null);

        // Close existing WebSocket
        if (chatWsRef.current) {
            chatWsRef.current.close();
        }

        const ws = new WebSocket(wsUrl("/api/v1/chat"));
        chatWsRef.current = ws;
        const assistantId = (Date.now() + 1).toString();
        let fullContent = "";

        // Connection timeout
        const connectionTimeout = setTimeout(() => {
            if (ws.readyState !== WebSocket.OPEN) {
                ws.close();
                setChatError("连接超时，请检查后端服务是否正常运行");
                setIsChatting(false);
            }
        }, 10000);

        ws.onopen = () => {
            clearTimeout(connectionTimeout);
            // Build history from existing messages
            const history = chatMessages.map((msg) => ({
                role: msg.role,
                content: msg.content,
            }));

            ws.send(
                JSON.stringify({
                    message: userMessage.content,
                    history,
                    kb_name: enableRag ? selectedKb : undefined,
                    enable_rag: enableRag && !!selectedKb,
                    enable_web_search: false, // 笔记本内禁用联网，使用纯 RAG 对话
                })
            );

            // Add placeholder assistant message
            setChatMessages((prev) => [
                ...prev,
                { id: assistantId, role: "assistant", content: "", isStreaming: true },
            ]);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "stream") {
                    fullContent += data.content;
                    setChatMessages((prev) =>
                        prev.map((msg) =>
                            msg.id === assistantId
                                ? { ...msg, content: fullContent }
                                : msg
                        )
                    );
                } else if (data.type === "result") {
                    setChatMessages((prev) =>
                        prev.map((msg) =>
                            msg.id === assistantId
                                ? { ...msg, content: data.content, isStreaming: false }
                                : msg
                        )
                    );
                    ws.close();
                } else if (data.type === "error") {
                    setChatError(data.message || "发生未知错误");
                    setChatMessages((prev) =>
                        prev.map((msg) =>
                            msg.id === assistantId
                                ? { ...msg, content: "抱歉，发生了错误，请重试。", isStreaming: false }
                                : msg
                        )
                    );
                }
            } catch {
                // Ignore parse errors for malformed messages
            }
        };

        ws.onerror = () => {
            clearTimeout(connectionTimeout);
            setChatError("WebSocket 连接失败，请检查网络或后端服务");
            setIsChatting(false);
        };

        ws.onclose = () => {
            clearTimeout(connectionTimeout);
            setIsChatting(false);
        };
    };

    // Fast Research - Quick web search using chat API with web_search enabled
    const handleFastResearch = () => {
        if (!searchQuery.trim() || isSearching) return;

        const url = wsUrl("/api/v1/chat");
        console.log("Fast Research connecting to:", url);

        setIsSearching(true);
        setChatError(null);

        const ws = new WebSocket(url);
        let fullResponse = "";

        // Connection timeout
        const connectionTimeout = setTimeout(() => {
            if (ws.readyState !== WebSocket.OPEN) {
                ws.close();
                setChatError("连接超时，请重试");
                alert(`Fast Research 连接超时: ${url}`);
                setIsSearching(false);
            }
        }, 15000);

        ws.onopen = () => {
            clearTimeout(connectionTimeout);
            console.log("Fast Research WS Connected");
            ws.send(JSON.stringify({
                message: `请搜索以下内容并返回相关网页链接：${searchQuery}`,
                history: [],
                kb_name: selectedKb || undefined,
                enable_rag: false,
                enable_web_search: true,
                model: "gpt-3.5-turbo",
                stream: true,
            }));
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "stream" && data.content) {
                    fullResponse += data.content;
                } else if (data.type === "result") {
                    // Use final result content if available
                    const finalContent = data.content || fullResponse;
                    // Parse URLs from the response
                    const urlRegex = /https?:\/\/[^\s\]\)]+/g;
                    const urls = finalContent.match(urlRegex) || [];
                    const uniqueUrls = [...new Set(urls)] as string[];

                    // Add as sources
                    const newSources: Source[] = uniqueUrls.slice(0, 10).map((url: string, idx: number) => ({
                        id: `web-${Date.now()}-${idx}`,
                        type: "web" as const,
                        title: url.replace(/https?:\/\/(www\.)?/, "").split("/")[0],
                        url: url,
                        selected: true,
                    }));

                    if (newSources.length > 0) {
                        setSources(prev => [...prev, ...newSources]);
                    }

                    // Also add the AI summary as a chat message
                    if (finalContent.trim()) {
                        setChatMessages(prev => [
                            ...prev,
                            { id: `fast-${Date.now()}`, role: "assistant", content: `**快速搜索结果：** ${searchQuery}\n\n${finalContent}` }
                        ]);
                    }

                    setSearchQuery("");
                    ws.close();
                    setIsSearching(false);
                } else if (data.type === "error") {
                    console.error("Fast Research Error:", data.content);
                    setChatError(data.content || "搜索失败");
                    ws.close();
                    setIsSearching(false);
                }
            } catch (e) {
                console.error("Fast research parse error:", e);
            }
        };

        ws.onerror = (e) => {
            clearTimeout(connectionTimeout);
            console.error("Fast Research WS Error:", e);
            setChatError("网络搜索连接失败");
            alert(`Fast Research WebSocket Error: 连接失败 ${url}`);
            setIsSearching(false);
        };

        ws.onclose = () => {
            clearTimeout(connectionTimeout);
            setIsSearching(false);
        };
    };

    // Toggle source selection
    const toggleSourceSelection = (sourceId: string) => {
        setSources(prev =>
            prev.map(s => (s.id === sourceId ? { ...s, selected: !s.selected } : s))
        );
    };

    // Select/deselect all sources
    const toggleAllSources = (selected: boolean) => {
        setSources(prev => prev.map(s => ({ ...s, selected })));
    };

    // Remove a source
    const removeSource = (sourceId: string) => {
        setSources(prev => prev.filter(s => s.id !== sourceId));
    };

    // Save content to notebook as a record
    const handleSaveToNotebook = async (content: string, title: string, type: "chat" | "research") => {
        if (!notebook) return;

        try {
            const res = await fetch(apiUrl(`/api/v1/notebook/${notebook.id}/records`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    type,
                    title,
                    user_query: title,
                    output: content,
                    metadata: {
                        sources: sources.filter(s => s.selected).map(s => ({ title: s.title, url: s.url })),
                    },
                    kb_name: selectedKb || undefined,
                }),
            });
            const data = await res.json();
            if (data.success) {
                fetchNotebook();
            }
        } catch (err) {
            console.error("Failed to save to notebook:", err);
        }
    };

    // Add note to notebook
    const handleAddNote = async () => {
        if (!noteTitle.trim() || !noteContent.trim() || !notebook) {
            alert("请填写标题和内容");
            return;
        }

        try {
            const res = await fetch(apiUrl(`/api/v1/notebook/${notebook.id}/records`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    type: "note",
                    title: noteTitle,
                    user_query: noteTitle,
                    output: noteContent,
                    metadata: {},
                }),
            });

            if (!res.ok) {
                const errorText = await res.text();
                console.error("Save note failed:", res.status, errorText);
                alert(`保存失败: ${res.status} - ${errorText}`);
                return;
            }

            const data = await res.json();
            if (data.success) {
                fetchNotebook();
                setShowAddNoteModal(false);
                setNoteTitle("");
                setNoteContent("");
            } else {
                alert("保存失败，请重试");
            }
        } catch (err) {
            console.error("Failed to add note:", err);
            alert(`保存失败: ${err}`);
        }
    };

    const handleQuickAddNote = async (content: string) => {
        if (!notebook) return;

        try {
            // Generate title using LLM for higher quality
            const res = await fetch(apiUrl("/api/v1/notebook/generate_title"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content })
            });
            const data = await res.json();
            const title = data.title || "AI 生成笔记";

            setNoteTitle(title);
            setNoteContent(content);
            setShowAddNoteModal(true);
        } catch (err) {
            console.error("Failed to generate title:", err);
            // Fallback to first line extraction
            const firstLine = content.split('\n')[0].replace(/^#+\s*/, '').trim();
            const autoTitle = firstLine.length > 30
                ? firstLine.substring(0, 30) + '...'
                : firstLine || "新 AI 笔记";
            setNoteTitle(autoTitle);
            setNoteContent(content);
            setShowAddNoteModal(true);
        }
    };

    // Delete record
    const handleDeleteRecord = async (recordId: string) => {
        if (!confirm("确定要删除这条记录吗？")) return;
        try {
            const res = await fetch(apiUrl(`/api/v1/notebook/${params.id}/records/${recordId}`), {
                method: "DELETE",
            });
            const data = await res.json();
            if (data.success) {
                fetchNotebook();
            }
        } catch (err) {
            console.error("Failed to delete record:", err);
        }
    };

    // Download record
    const handleDownloadRecord = (record: any) => {
        const content = `# ${record.title}\n\n${record.output || record.user_query}\n\n---\nCreated: ${new Date(record.created_at * 1000).toLocaleString()}`;
        const blob = new Blob([content], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${record.title || "笔记"}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };


    // Add URL as source
    const handleAddSourceUrl = () => {
        if (!sourceUrl.trim()) return;

        const newSource: Source = {
            id: `url-${Date.now()}`,
            type: "web",
            title: sourceUrl,
            url: sourceUrl,
            selected: true,
        };
        setSources(prev => [...prev, newSource]);
        setSourceUrl("");
        setShowAddSourceModal(false);
    };
    const cancelResearch = () => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: "cancel" }));
        }
        setResearchRunning(false);
        setIsChatting(false);
        setResearchPhase("idle");
        setResearchStartTime(null);
        setEstimatedTimeRemaining("");
        setChatMessages((prev) =>
            prev.map((msg) =>
                msg.isStreaming
                    ? { ...msg, content: msg.content + "\n\n[研究已取消]", isStreaming: false }
                    : msg
            )
        );
    };


    // Research function with enhanced error handling
    // Can be called with optional topic parameter (for Deep Research from chat)
    const startResearchWithTopic = (topic?: string) => {
        const researchTopicToUse = topic || researchTopic;
        if (!researchTopicToUse.trim() || researchRunning) return;

        if (wsRef.current) wsRef.current.close();

        const url = wsUrl("/api/v1/research/run");
        console.log("Deep Research connecting to:", url);

        setResearchRunning(true);
        setResearchStartTime(Date.now());
        setEstimatedTimeRemaining("");
        setResearchReport("");
        setResearchError(null);
        setIsChatting(true); // Show loading state in chat if triggered from there

        // Generate a unique ID for this research session's streaming message
        const streamingMsgId = `research-${Date.now()}`;

        // Always create a streaming message when starting research
        setChatMessages((prev) => {
            // Check if there's already a streaming message (from handleSendChat)
            const hasStreaming = prev.some(msg => msg.isStreaming);
            if (hasStreaming) {
                return prev;
            }
            // Add a new streaming message
            return [
                ...prev,
                { id: streamingMsgId, role: "assistant" as const, content: "🚀 正在启动深度研究...", isStreaming: true },
            ];
        });

        const ws = new WebSocket(url);
        wsRef.current = ws;

        // Connection timeout (15 seconds)
        const connectionTimeout = setTimeout(() => {
            if (ws.readyState !== WebSocket.OPEN) {
                ws.close();
                setResearchError("连接超时，请检查后端服务是否正常运行");
                alert(`Deep Research 连接超时: ${url}`);
                setResearchRunning(false);
                setIsChatting(false);
            }
        }, 15000);

        // Research timeout (45 minutes max for complex topics)
        const researchTimeout = setTimeout(() => {
            if (wsRef.current === ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
                setResearchError("研究超时 - 请尝试使用更简单的主题或较少的研究深度");
                alert("Deep Research 研究超时");
                setResearchRunning(false);
                setIsChatting(false);
            }
        }, 2700000);

        ws.onopen = () => {
            clearTimeout(connectionTimeout);
            console.log("Deep Research WS Connected");
            ws.send(
                JSON.stringify({
                    topic: researchTopicToUse,
                    kb_name: selectedKb,
                    plan_mode: planMode,
                    enabled_tools: enabledTools,
                    skip_rephrase: !enableOptimization,
                })
            );
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "result") {
                    clearTimeout(researchTimeout);
                    const report = data.report || "";
                    setResearchReport(report);
                    setResearchRunning(false);
                    setIsChatting(false);
                    setResearchPhase("idle");
                    setResearchProgress({ current: 0, total: 0 });
                    setCurrentSubTopic("");
                    setResearchStartTime(null);
                    setEstimatedTimeRemaining("");

                    // Update chat with research result - ensure report is displayed
                    if (report) {
                        setChatMessages((prev) => {
                            // Try to update existing streaming message
                            const hasStreaming = prev.some(msg => msg.isStreaming);
                            if (hasStreaming) {
                                return prev.map((msg) =>
                                    msg.isStreaming
                                        ? { ...msg, content: `**📚 深度研究完成**\n\n${report}`, isStreaming: false }
                                        : msg
                                );
                            }
                            // If no streaming message, add a new one
                            return [
                                ...prev,
                                { id: `result-${Date.now()}`, role: "assistant" as const, content: `**📚 深度研究完成**\n\n${report}` }
                            ];
                        });
                    }

                    // Extract sources from metadata and add to Sources panel
                    if (data.metadata) {
                        const newSources: Source[] = [];

                        // Handle web sources
                        if (data.metadata.web_sources && Array.isArray(data.metadata.web_sources)) {
                            data.metadata.web_sources.forEach((s: any, idx: number) => {
                                newSources.push({
                                    id: `research-web-${Date.now()}-${idx}`,
                                    type: "web" as const,
                                    title: s.title || s.url || `网络来源 ${idx + 1}`,
                                    url: s.url,
                                    selected: true,
                                });
                            });
                        }

                        // Handle RAG sources
                        if (data.metadata.rag_sources && Array.isArray(data.metadata.rag_sources)) {
                            data.metadata.rag_sources.forEach((s: any, idx: number) => {
                                newSources.push({
                                    id: `research-rag-${Date.now()}-${idx}`,
                                    type: "kb" as const,
                                    title: s.title || s.source || `知识库来源 ${idx + 1}`,
                                    url: s.url || "",
                                    selected: true,
                                });
                            });
                        }

                        // Handle general sources array
                        if (data.metadata.sources && Array.isArray(data.metadata.sources)) {
                            data.metadata.sources.forEach((s: any, idx: number) => {
                                newSources.push({
                                    id: `research-src-${Date.now()}-${idx}`,
                                    type: (s.type === "web" ? "web" : "kb") as "web" | "kb",
                                    title: s.title || s.url || `来源 ${idx + 1}`,
                                    url: s.url || "",
                                    selected: true,
                                });
                            });
                        }

                        if (newSources.length > 0) {
                            setSources(prev => [...prev, ...newSources]);
                        }
                    }
                } else if (data.type === "error") {
                    clearTimeout(researchTimeout);
                    console.error("Deep Research Error:", data);
                    setResearchError(data.content || data.message || "研究过程中发生错误");
                    setResearchRunning(false);
                    setIsChatting(false);
                    setResearchPhase("idle");
                    // Update chat with error
                    setChatMessages((prev) =>
                        prev.map((msg) =>
                            msg.isStreaming
                                ? { ...msg, content: `❌ 研究失败: ${data.content || data.message}`, isStreaming: false }
                                : msg
                        )
                    );
                } else if (data.type === "progress") {
                    // Handle progress events from backend
                    const stage = data.stage as "planning" | "researching" | "reporting";
                    if (stage) {
                        setResearchPhase(stage);
                    }

                    // Update progress based on status
                    const status = data.status as string;

                    if (status === "planning_started") {
                        setResearchPhase("planning");
                        updateStreamingMessage("📋 正在分析研究主题...");
                    } else if (status === "decompose_completed") {
                        const totalBlocks = data.generated_subtopics || data.total_blocks || 0;
                        setResearchProgress({ current: 0, total: totalBlocks });
                        updateStreamingMessage(`📋 已分解为 ${totalBlocks} 个子主题`);
                        // Store subtopics if available
                        if (data.sub_topics && Array.isArray(data.sub_topics)) {
                            setSubTopics(data.sub_topics.map((t: any) => t.title || t));
                        }
                    } else if (status === "researching_started") {
                        setResearchPhase("researching");
                        const totalBlocks = data.total_blocks || researchProgress.total;
                        setResearchProgress(prev => ({ ...prev, total: totalBlocks }));
                        updateStreamingMessage(`🔬 开始深度研究 (${totalBlocks} 个子主题)...`);
                    } else if (status === "block_started") {
                        const currentBlock = data.current_block || researchProgress.current + 1;
                        const totalBlocks = data.total_blocks || researchProgress.total;
                        setResearchProgress({ current: currentBlock, total: totalBlocks });
                        setCurrentSubTopic(data.sub_topic || "");
                        updateStreamingMessage(`🔬 正在研究 (${currentBlock}/${totalBlocks}): ${data.sub_topic || ""}`);

                        // Calculate ETA
                        if (researchStartTime && currentBlock > 0 && totalBlocks > 0) {
                            const progressPercentage = (currentBlock / totalBlocks) * 100;
                            const elapsed = Date.now() - researchStartTime;
                            const estimatedTotal = elapsed / (progressPercentage / 100);
                            const remaining = estimatedTotal - elapsed;
                            if (remaining > 0) {
                                const minutes = Math.floor(remaining / 60000);
                                const seconds = Math.floor((remaining % 60000) / 1000);
                                setEstimatedTimeRemaining(`${minutes}分${seconds}秒`);
                            }
                        }
                    } else if (status === "block_completed") {
                        const currentBlock = data.current_block || researchProgress.current;
                        const totalBlocks = data.total_blocks || researchProgress.total;
                        setResearchProgress({ current: currentBlock, total: totalBlocks });
                    } else if (status === "reporting_started") {
                        setResearchPhase("reporting");
                        setCurrentSubTopic("");
                        updateStreamingMessage("📝 正在生成研究报告...");
                    } else if (status === "writing_section") {
                        const section = data.section_title || data.section || "";
                        updateStreamingMessage(`📝 正在撰写: ${section}`);
                    }
                } else if (data.type === "status") {
                    // Handle status updates
                    if (data.content === "started") {
                        setResearchPhase("planning");
                        updateStreamingMessage("🚀 深度研究已启动...");
                    }
                }
                // Silently ignore "log" and "ping" types
            } catch (e) {
                console.error("Deep research parse error:", e);
            }
        };

        // Helper function to update the streaming message
        const updateStreamingMessage = (content: string) => {
            setChatMessages((prev) =>
                prev.map((msg) =>
                    msg.isStreaming
                        ? { ...msg, content }
                        : msg
                )
            );
        };

        ws.onerror = (e) => {
            clearTimeout(connectionTimeout);
            clearTimeout(researchTimeout);
            console.error("Deep Research WS Error:", e);
            setResearchError("WebSocket 连接失败，请检查网络或后端服务");
            alert(`Deep Research WebSocket 错误: 连接失败 ${url}`);
            setResearchRunning(false);
            setIsChatting(false);
            setChatMessages((prev) =>
                prev.map((msg) =>
                    msg.isStreaming
                        ? { ...msg, content: "❌ 研究连接失败", isStreaming: false }
                        : msg
                )
            );
        };

        ws.onclose = () => {
            clearTimeout(connectionTimeout);
            clearTimeout(researchTimeout);
            setResearchRunning(false);
            setIsChatting(false);

            // If connection closes while still streaming (no result received), mark as failed
            setChatMessages((prev) => {
                const hasStreaming = prev.some(msg => msg.isStreaming);
                if (hasStreaming) {
                    return prev.map(msg =>
                        msg.isStreaming
                            ? { ...msg, content: msg.content + "\n\n[连接断开，未收到完整报告。请尝试刷新页面。]", isStreaming: false }
                            : msg
                    );
                }
                return prev;
            });
        };
    };

    // Export functions
    const getExportMarkdown = async () => {
        if (exportContentSource === "research") {
            return researchReport;
        }

        const selectedSources = sources.filter((source) => source.selected);
        if (selectedSources.length === 0) {
            alert("请先选择来源");
            return "";
        }

        const res = await fetch(apiUrl("/api/v1/research/compose_from_sources"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                sources: selectedSources.map((source) => ({
                    type: source.type,
                    title: source.title,
                    url: source.url,
                })),
                topic: notebook?.name || undefined,
            }),
        });

        if (!res.ok) throw new Error("生成失败");

        const data = await res.json();
        return data.markdown || "";
    };

    const getSelectedPptStylePrompt = () => {
        const selected = pptStyleTemplates.find((tmpl) => tmpl.id === selectedPptStyleId);
        return selected?.prompt || "";
    };

    const getSourcesStylePrompt = async () => {
        const selectedSources = sources.filter((source) => source.selected);
        if (selectedSources.length === 0) {
            alert("请先选择来源以生成风格");
            return "";
        }
        const res = await fetch(apiUrl("/api/v1/research/ppt_style_from_sources"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                sources: selectedSources.map((source) => ({
                    type: source.type,
                    title: source.title,
                    url: source.url,
                })),
                topic: notebook?.name || undefined,
            }),
        });
        if (!res.ok) throw new Error("生成失败");
        const data = await res.json();
        return data.style_prompt || "";
    };

    const getPromptForSource = async (source: "preset" | "sources") => {
        if (source === "preset") {
            return getSelectedPptStylePrompt();
        }
        return getSourcesStylePrompt();
    };

    const getPptStylePrompt = async () => {
        if (pptStyleMode === "preset") {
            return getPromptForSource("preset");
        }

        if (pptStyleMode === "sources") {
            return getPromptForSource("sources");
        }

        return "";
    };

    const handlePreviewPptStyle = async () => {
        if (pptStyleMode === "template") {
            setPptStylePreviewError("模板模式暂不支持风格预览");
            return;
        }

        setPptStylePreviewLoading(true);
        setPptStylePreviewError("");
        try {
            const stylePrompt = await getPptStylePrompt();
            if (pptStyleMode === "preset" && !stylePrompt) {
                alert("请选择风格模板");
                return;
            }
            if (pptStyleMode === "sources" && !stylePrompt) {
                return;
            }

            const res = await fetch(apiUrl("/api/v1/research/ppt_style_preview"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    style_prompt: stylePrompt || undefined,
                }),
            });

            if (!res.ok) throw new Error("预览失败");
            const data = await res.json();
            setPptStylePreviewSvg(data.preview_svg || "");
        } catch (err) {
            console.error("PPT style preview failed:", err);
            setPptStylePreviewError("风格预览失败");
        } finally {
            setPptStylePreviewLoading(false);
        }
    };

    const handleExportPdf = async () => {
        setIsExporting(true);
        try {
            const markdown = await getExportMarkdown();
            if (!markdown) return;

            const res = await fetch(apiUrl("/api/v1/research/export_pdf"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    markdown,
                    title: notebook?.name || undefined,
                }),
            });

            if (!res.ok) throw new Error("导出失败");

            const data = await res.json();
            if (data.download_url) {
                const a = document.createElement("a");
                a.href = apiUrl(data.download_url);
                a.download = data.filename || `${notebook?.name}.pdf`;
                a.click();
            }
        } catch (err) {
            console.error("PDF export failed:", err);
        } finally {
            setIsExporting(false);
        }
    };

    const handleExportPptx = async () => {
        setIsExporting(true);
        try {
            const markdown = await getExportMarkdown();
            if (!markdown) return;

            let stylePrompt = "";
            if (pptStyleMode === "template") {
                if (!selectedPptTemplate) {
                    alert("请选择 PPT 模板");
                    return;
                }
                if (pptTemplateUseLlm) {
                    stylePrompt = await getPromptForSource(pptTemplatePromptSource);
                    if (!stylePrompt) {
                        return;
                    }
                }
            } else {
                stylePrompt = await getPptStylePrompt();
                if (pptStyleMode === "preset" && !stylePrompt) {
                    alert("请选择风格模板");
                    return;
                }
                if (pptStyleMode === "sources" && !stylePrompt) {
                    return;
                }
            }

            const res = await fetch(apiUrl("/api/v1/research/export_pptx"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    markdown,
                    title: notebook?.name || undefined,
                    style_prompt: stylePrompt || undefined,
                    template_name: pptStyleMode === "template" ? selectedPptTemplate : undefined,
                }),
            });

            if (!res.ok) throw new Error("导出失败");

            const data = await res.json();
            if (data.download_url) {
                const a = document.createElement("a");
                a.href = apiUrl(data.download_url);
                a.download = data.filename || `${notebook?.name}.pptx`;
                a.click();
            }
        } catch (err) {
            console.error("PPTX export failed:", err);
        } finally {
            setIsExporting(false);
        }
    };

    const handleGenerateMindmap = async () => {
        setIsExporting(true);
        try {
            const markdown = await getExportMarkdown();
            if (!markdown) return;

            const res = await fetch(apiUrl("/api/v1/research/export_mindmap"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    markdown,
                    use_llm: false,
                }),
            });

            if (!res.ok) throw new Error("生成失败");

            const data = await res.json();
            setMindmapCode(data.mindmap || "");
            setStudioMode("mindmap");
        } catch (err) {
            console.error("Mindmap generation failed:", err);
        } finally {
            setIsExporting(false);
        }
    };

    const renderExportSourceToggle = () => (
        <div className="flex items-center justify-center gap-2 text-xs text-slate-500">
            <span>内容来源</span>
            <div className="flex rounded-lg bg-slate-100 p-1">
                <button
                    onClick={() => setExportContentSource("research")}
                    className={`px-2 py-1 rounded-md transition-colors ${exportContentSource === "research"
                        ? "bg-white text-slate-700 shadow-sm"
                        : "text-slate-400 hover:text-slate-600"
                        }`}
                >
                    深度研究
                </button>
                <button
                    onClick={() => setExportContentSource("sources")}
                    className={`px-2 py-1 rounded-md transition-colors ${exportContentSource === "sources"
                        ? "bg-white text-slate-700 shadow-sm"
                        : "text-slate-400 hover:text-slate-600"
                        }`}
                >
                    已选来源
                </button>
            </div>
        </div>
    );

    const renderPptStylePanel = () => (
        <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 text-left">
            <div className="flex items-center justify-between mb-3">
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    PPT 风格
                </div>
            </div>
            <div className="flex items-center gap-2 mb-3 text-xs text-slate-500">
                <span>风格来源</span>
                <div className="flex rounded-lg bg-white p-1 shadow-sm">
                    {[
                        { id: "default", label: "默认" },
                        { id: "preset", label: "预设" },
                        { id: "template", label: "模板" },
                        { id: "sources", label: "来源" },
                    ].map((item) => (
                        <button
                            key={item.id}
                            onClick={() => setPptStyleMode(item.id as typeof pptStyleMode)}
                            className={`px-2.5 py-1 rounded-md transition-colors ${pptStyleMode === item.id
                                ? "bg-slate-900 text-white"
                                : "text-slate-500 hover:text-slate-700"
                                }`}
                        >
                            {item.label}
                        </button>
                    ))}
                </div>
            </div>

            {pptStyleMode === "default" && (
                <p className="text-xs text-slate-500">
                    使用系统默认风格与布局。
                </p>
            )}

            {pptStyleMode === "preset" && (
                <div className="space-y-2">
                    <select
                        value={selectedPptStyleId}
                        onChange={(e) => setSelectedPptStyleId(e.target.value)}
                        className="w-full text-xs bg-white border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                    >
                        {pptStyleTemplates.length === 0 && (
                            <option value="">暂无预设</option>
                        )}
                        {pptStyleTemplates.map((tmpl) => (
                            <option key={tmpl.id} value={tmpl.id}>
                                {tmpl.name}
                            </option>
                        ))}
                    </select>
                    <p className="text-[11px] text-slate-400 line-clamp-2">
                        {getSelectedPptStylePrompt() || "选择预设风格后，将使用对应的提示词优化演示风格。"}
                    </p>
                </div>
            )}

            {pptStyleMode === "template" && (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => pptTemplateInputRef.current?.click()}
                            disabled={pptTemplateUploading}
                            className="px-3 py-2 text-xs rounded-lg bg-white border border-slate-200 hover:border-orange-300 hover:bg-orange-50 transition-colors disabled:opacity-50"
                        >
                            {pptTemplateUploading ? "上传中..." : "上传模板"}
                        </button>
                        <input
                            ref={pptTemplateInputRef}
                            type="file"
                            accept=".pptx"
                            className="hidden"
                            onChange={handleUploadPptTemplate}
                        />
                        <span className="text-[11px] text-slate-400">支持 .pptx</span>
                    </div>
                    <select
                        value={selectedPptTemplate}
                        onChange={(e) => setSelectedPptTemplate(e.target.value)}
                        className="w-full text-xs bg-white border border-slate-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                    >
                        {pptTemplates.length === 0 && (
                            <option value="">暂无模板</option>
                        )}
                        {pptTemplates.map((tmpl) => (
                            <option key={tmpl.name} value={tmpl.name}>
                                {tmpl.name}
                            </option>
                        ))}
                    </select>
                    <label className="flex items-center gap-2 text-xs text-slate-500">
                        <input
                            type="checkbox"
                            checked={pptTemplateUseLlm}
                            onChange={(e) => setPptTemplateUseLlm(e.target.checked)}
                            className="rounded border-slate-300 text-orange-600 focus:ring-orange-500"
                        />
                        使用 LLM 生成结构
                    </label>
                    {pptTemplateUseLlm && (
                        <div className="flex items-center gap-2 text-xs text-slate-500">
                            <span>结构来源</span>
                            <div className="flex rounded-lg bg-white p-1 shadow-sm">
                                {[
                                    { id: "preset", label: "预设" },
                                    { id: "sources", label: "来源" },
                                ].map((item) => (
                                    <button
                                        key={item.id}
                                        onClick={() => setPptTemplatePromptSource(item.id as "preset" | "sources")}
                                        className={`px-2 py-1 rounded-md transition-colors ${pptTemplatePromptSource === item.id
                                            ? "bg-slate-900 text-white"
                                            : "text-slate-500 hover:text-slate-700"
                                            }`}
                                    >
                                        {item.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {pptStyleMode === "sources" && (
                <div className="space-y-2">
                    <p className="text-xs text-slate-500">
                        根据已选来源生成风格提示词。
                    </p>
                    <div className="text-[11px] text-slate-400">
                        {hasSelectedSources ? `已选来源 ${sources.filter((s) => s.selected).length} 个` : "暂无已选来源"}
                    </div>
                </div>
            )}

            {pptStyleMode !== "template" && (
                <div className="mt-3">
                    <button
                        onClick={handlePreviewPptStyle}
                        disabled={pptStylePreviewLoading}
                        className="px-3 py-2 text-xs rounded-lg bg-white border border-slate-200 hover:border-orange-300 hover:bg-orange-50 transition-colors disabled:opacity-50"
                    >
                        {pptStylePreviewLoading ? "生成预览..." : "预览风格"}
                    </button>
                    {pptStylePreviewError && (
                        <p className="text-[11px] text-rose-500 mt-2">{pptStylePreviewError}</p>
                    )}
                    {pptStylePreviewSvg && (
                        <div
                            className="mt-3 rounded-lg border border-slate-200 overflow-hidden bg-white"
                            dangerouslySetInnerHTML={{ __html: pptStylePreviewSvg }}
                        />
                    )}
                </div>
            )}
        </div>
    );

    if (loading) {
        return (
            <div className="h-screen flex items-center justify-center bg-slate-50">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            </div>
        );
    }

    if (!notebook) {
        return null;
    }

    return (
        <div className="h-screen flex bg-slate-50">
            {/* Left Panel - Sources */}
            <div
                className={`flex flex-col bg-white border-r border-slate-200 transition-all duration-300 ${leftCollapsed ? "w-0 overflow-hidden" : "w-72"
                    }`}
            >
                {/* Header */}
                <div
                    className="p-4 border-b border-slate-200"
                    style={{ backgroundColor: `${notebook.color}08` }}
                >
                    <div className="flex items-center gap-3 mb-3">
                        <button
                            onClick={() => router.push("/notebooks")}
                            className="p-1.5 hover:bg-slate-100 rounded-lg"
                        >
                            <ArrowLeft className="w-4 h-4 text-slate-500" />
                        </button>
                        <div
                            className="w-8 h-8 rounded-lg flex items-center justify-center"
                            style={{
                                backgroundColor: `${notebook.color}20`,
                                color: notebook.color,
                            }}
                        >
                            <BookOpen className="w-4 h-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <h2 className="font-bold text-slate-900 truncate text-sm">
                                {notebook.name}
                            </h2>
                        </div>
                    </div>

                    {/* Add Source Button */}
                    <button
                        onClick={() => setShowAddSourceModal(true)}
                        className="w-full py-2 px-3 border border-dashed border-slate-300 rounded-lg text-sm text-slate-500 hover:border-slate-400 hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
                    >
                        <Plus className="w-4 h-4" />
                        添加来源
                    </button>
                </div>

                {/* Context Settings */}
                <div className="p-3 border-b border-slate-200 space-y-2">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-slate-600">
                            <Database className="w-4 h-4" />
                            <span className="text-sm font-medium">知识库 (RAG)</span>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                            <input
                                type="checkbox"
                                checked={enableRag}
                                onChange={(e) => setEnableRag(e.target.checked)}
                                className="sr-only peer"
                            />
                            <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                        </label>
                    </div>
                </div>

                {/* Research Hub */}
                <div className="p-3 border-b border-slate-200 bg-slate-50/50">
                    {/* Mode Switch */}
                    <div className="flex bg-slate-100 p-1 rounded-lg mb-3">
                        <button
                            onClick={() => setResearchMode("fast")}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-medium transition-all ${researchMode === "fast"
                                ? "bg-white text-emerald-700 shadow-sm"
                                : "text-slate-500 hover:text-slate-700"
                                }`}
                        >
                            <Zap className="w-3.5 h-3.5" />
                            Fast Research
                        </button>
                        <button
                            onClick={() => setResearchMode("deep")}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-medium transition-all ${researchMode === "deep"
                                ? "bg-white text-purple-700 shadow-sm"
                                : "text-slate-500 hover:text-slate-700"
                                }`}
                        >
                            <Microscope className="w-3.5 h-3.5" />
                            Deep Research
                        </button>
                    </div>

                    {/* Input Area */}
                    <div className="space-y-3">
                        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-blue-500/20 focus-within:border-blue-500">
                            {researchMode === "fast" ? (
                                <Globe className="w-4 h-4 text-emerald-500 shrink-0" />
                            ) : (
                                <Microscope className="w-4 h-4 text-purple-500 shrink-0" />
                            )}
                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                        if (researchMode === "fast") handleFastResearch();
                                        else if (researchMode === "deep") startResearchWithTopic(searchQuery);
                                    }
                                }}
                                placeholder={researchMode === "fast" ? "搜索关键词..." : "输入研究主题..."}
                                className="flex-1 bg-transparent text-sm outline-none w-full min-w-0"
                            />
                        </div>

                        {/* Deep Research Config (Only visible in Deep mode) */}
                        {researchMode === "deep" && (
                            <div className="text-xs space-y-3 pt-2 px-1 border-t border-slate-200/50">
                                <div className="space-y-1.5">
                                    <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">计划深度</div>
                                    <div className="grid grid-cols-4 gap-1">
                                        {(["quick", "medium", "deep", "auto"] as const).map((mode) => (
                                            <button
                                                key={mode}
                                                onClick={() => setPlanMode(mode)}
                                                className={`px-1 py-1 rounded text-center transition-colors ${planMode === mode
                                                    ? "bg-purple-100 text-purple-700 font-medium"
                                                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                                    }`}
                                            >
                                                {mode === "quick" ? "快速" : mode === "medium" ? "标准" : mode === "deep" ? "深入" : "自动"}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <input
                                        type="checkbox"
                                        id="opt-toggle"
                                        checked={enableOptimization}
                                        onChange={(e) => setEnableOptimization(e.target.checked)}
                                        className="rounded border-slate-300 text-purple-600 focus:ring-purple-500"
                                    />
                                    <label htmlFor="opt-toggle" className="text-slate-600 cursor-pointer select-none">使用 AI 优化主题</label>
                                </div>
                            </div>
                        )}

                        {/* Action Button */}
                        <button
                            onClick={() => {
                                if (researchMode === "fast") handleFastResearch();
                                else startResearchWithTopic(searchQuery);
                            }}
                            disabled={isSearching || researchRunning || !searchQuery.trim()}
                            className={`w-full py-2 px-4 rounded-lg text-sm font-medium text-white transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 ${researchMode === "fast"
                                ? "bg-emerald-600 hover:bg-emerald-700"
                                : "bg-purple-600 hover:bg-purple-700"
                                }`}
                        >
                            {isSearching || researchRunning ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    {researchMode === "fast" ? "搜索中..." : "研究中..."}
                                </>
                            ) : (
                                <>
                                    {researchMode === "fast" ? <Search className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
                                    {researchMode === "fast" ? "搜索来源" : "开始深度研究"}
                                </>
                            )}
                        </button>

                        {/* Deep Research Progress Indicator */}
                        {researchRunning && researchMode === "deep" && (
                            <div className="mt-3 p-3 bg-purple-50 border border-purple-200 rounded-lg space-y-2 animate-in fade-in duration-300">
                                {/* Phase Indicator */}
                                <div className="flex items-center gap-2">
                                    <div className={`w-2 h-2 rounded-full animate-pulse ${researchPhase === "planning" ? "bg-blue-500" :
                                        researchPhase === "researching" ? "bg-purple-500" :
                                            researchPhase === "reporting" ? "bg-emerald-500" :
                                                "bg-slate-400"
                                        }`} />
                                    <span className="text-xs font-medium text-slate-700">
                                        {researchPhase === "planning" ? "📋 规划中" :
                                            researchPhase === "researching" ? "🔬 研究中" :
                                                researchPhase === "reporting" ? "📝 生成报告" :
                                                    "准备中"}
                                    </span>
                                </div>

                                {/* Progress Bar (only show during researching phase) */}
                                {researchPhase === "researching" && researchProgress.total > 0 && (
                                    <div className="space-y-1">
                                        <div className="flex justify-between text-[10px] text-slate-500">
                                            <span>子主题进度</span>
                                            <div className="flex items-center gap-2">
                                                <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                                    <div
                                                        className="h-full bg-blue-500 rounded-full transition-all duration-300"
                                                        style={{ width: `${researchProgress.current}%` }}
                                                    />
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs text-slate-400 tabular-nums">
                                                        {researchProgress.current}%
                                                    </span>
                                                    {estimatedTimeRemaining && (
                                                        <span className="text-[10px] text-slate-400">
                                                            预计剩余 {estimatedTimeRemaining}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* Current Sub-topic */}
                                {currentSubTopic && (
                                    <div className="text-[10px] text-slate-600 truncate" title={currentSubTopic}>
                                        当前: {currentSubTopic}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                {/* Sources List Header */}
                <div className="px-3 pt-3 pb-2 flex items-center justify-between">
                    <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                        已选来源 ({sources.filter(s => s.selected).length})
                    </div>
                    {sources.length > 0 && (
                        <button
                            onClick={() => toggleAllSources(true)}
                            className="text-xs text-blue-600 hover:underline"
                        >
                            全选
                        </button>
                    )}
                </div>

                {/* Sources List Content */}
                <div className="flex-1 overflow-y-auto px-3 pb-3">
                    {sources.length === 0 ? (
                        <div className="text-center py-8">
                            <FileText className="w-10 h-10 text-slate-200 mx-auto mb-3" />
                            <p className="text-sm text-slate-500 mb-1">暂无来源</p>
                            <p className="text-xs text-slate-400">
                                使用 Fast Research 搜索或点击上方按钮添加
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-1">
                            {sources.map((source) => (
                                <div
                                    key={source.id}
                                    className="flex items-center gap-2 p-2 rounded-lg hover:bg-slate-50 group"
                                >
                                    <button
                                        onClick={() => toggleSourceSelection(source.id)}
                                        className="shrink-0"
                                    >
                                        {source.selected ? (
                                            <CheckSquare className="w-4 h-4 text-blue-600" />
                                        ) : (
                                            <Square className="w-4 h-4 text-slate-300" />
                                        )}
                                    </button>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm text-slate-700 truncate">{source.title}</p>
                                        {source.url && (
                                            <p className="text-xs text-slate-400 truncate">{source.url}</p>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => removeSource(source.id)}
                                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-50 rounded"
                                    >
                                        <X className="w-3 h-3 text-red-500" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* KB as Source */}
                    {kbs.length > 0 && (
                        <div className="mt-4 pt-4 border-t border-slate-200">
                            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                                知识库
                            </div>
                            <select
                                value={selectedKb}
                                onChange={(e) => setSelectedKb(e.target.value)}
                                className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 outline-none"
                            >
                                <option value="">不使用知识库</option>
                                {kbs.map((kb) => (
                                    <option key={kb.name} value={kb.name}>
                                        {kb.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}

                </div>

                {/* Collapse Button */}
                <button
                    onClick={() => setLeftCollapsed(true)}
                    className="p-2 border-t border-slate-200 text-slate-400 hover:bg-slate-50 flex items-center justify-center"
                >
                    <ChevronLeft className="w-4 h-4" />
                </button>
            </div>

            {/* Left Expand Button */}
            {leftCollapsed && (
                <button
                    onClick={() => setLeftCollapsed(false)}
                    className="w-8 bg-white border-r border-slate-200 flex items-center justify-center text-slate-400 hover:bg-slate-50"
                >
                    <ChevronRight className="w-4 h-4" />
                </button>
            )}

            {/* Middle Panel - Chat */}
            <div className="flex-1 flex flex-col min-w-0">
                {/* Chat Header */}
                <div className="p-4 border-b border-slate-200 bg-white">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <h3 className="font-semibold text-slate-900">对话</h3>
                            {sources.filter(s => s.selected).length > 0 && (
                                <span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full font-medium">
                                    引用 {sources.filter(s => s.selected).length} 个来源
                                </span>
                            )}
                        </div>
                    </div>
                </div>

                {/* Chat Messages */}
                <div
                    ref={chatContainerRef}
                    className="flex-1 overflow-y-auto p-4 space-y-4"
                >
                    {chatMessages.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-center">
                            <Bot className="w-12 h-12 text-slate-200 mb-3" />
                            <p className="text-slate-500 text-sm">开始对话吧</p>
                            <p className="text-slate-400 text-xs mt-1">
                                输入问题，AI 将基于知识库回答
                            </p>
                        </div>
                    ) : (
                        chatMessages.map((msg) => (
                            <div
                                key={msg.id}
                                className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"
                                    }`}
                            >
                                {msg.role === "assistant" && (
                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0">
                                        <Bot className="w-4 h-4 text-white" />
                                    </div>
                                )}
                                <div
                                    className={`max-w-[70%] rounded-2xl px-4 py-3 ${msg.role === "user"
                                        ? "bg-blue-600 text-white rounded-br-none"
                                        : "bg-white border border-slate-200 text-slate-700 rounded-bl-none"
                                        }`}
                                >
                                    {msg.role === "assistant" ? (
                                        <>
                                            <div className="prose prose-sm prose-slate max-w-none">
                                                <ReactMarkdown
                                                    remarkPlugins={[remarkMath]}
                                                    rehypePlugins={[rehypeKatex]}
                                                >
                                                    {processLatexContent(msg.content)}
                                                </ReactMarkdown>
                                            </div>
                                            {!msg.isStreaming && (
                                                <div className="mt-2 flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                                                    <button
                                                        onClick={() => handleQuickAddNote(msg.content)}
                                                        className="flex items-center gap-1 text-xs text-slate-500 hover:text-blue-600 transition-colors"
                                                        title="添加到笔记"
                                                    >
                                                        <FilePlus className="w-3.5 h-3.5" />
                                                        <span>存为笔记</span>
                                                    </button>
                                                </div>
                                            )}
                                        </>
                                    ) : (
                                        <p className="text-sm">{msg.content}</p>
                                    )}
                                </div>
                                {
                                    msg.role === "user" && (
                                        <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
                                            <User className="w-4 h-4 text-slate-500" />
                                        </div>
                                    )
                                }
                            </div>
                        ))
                    )}
                </div>

                {/* Chat Error Display */}
                {chatError && (
                    <div className="mx-4 mb-2 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
                        <span className="text-red-600 text-sm flex-1">{chatError}</span>
                        <button
                            onClick={() => setChatError(null)}
                            className="text-red-400 hover:text-red-600 text-lg leading-none"
                        >
                            ×
                        </button>
                    </div>
                )}

                {/* Chat Input */}
                <div className="p-4 border-t border-slate-200 bg-white">
                    <div className="flex gap-2">
                        <input
                            type="text"
                            value={chatInput}
                            onChange={(e) => setChatInput(e.target.value)}
                            onKeyDown={(e) =>
                                e.key === "Enter" && !e.shiftKey && handleSendChat()
                            }
                            placeholder="输入你的问题..."
                            disabled={isChatting}
                            className="flex-1 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none disabled:opacity-50"
                        />
                        <button
                            onClick={handleSendChat}
                            disabled={!chatInput.trim() || isChatting}
                            className="px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {isChatting ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : (
                                <Send className="w-5 h-5" />
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {/* Right Panel - Studio */}
            <div
                className={`flex flex-col bg-white border-l border-slate-200 transition-all duration-300 ${rightCollapsed ? "w-0 overflow-hidden" : "w-80"
                    }`}
            >
                {/* Studio Header */}
                <div className="p-4 border-b border-slate-200">
                    <h3 className="font-semibold text-slate-900">Studio</h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                        研究、导出与可视化
                    </p>
                </div>

                {/* Studio Content */}
                <div className="flex-1 overflow-y-auto p-4">
                    {studioMode === "idle" && (
                        <div className="space-y-4">
                            {/* Core Features */}
                            <div>
                                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                                    核心功能
                                </div>
                                <div className="space-y-2">

                                    {/* Question Generator */}
                                    <button
                                        onClick={() => setStudioMode("question")}
                                        disabled={notebook.records.length === 0 && !researchReport}
                                        className="w-full p-3 rounded-xl border border-slate-200 hover:border-purple-300 hover:bg-purple-50/50 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="w-9 h-9 rounded-lg bg-purple-100 flex items-center justify-center">
                                                <PenTool className="w-4 h-4 text-purple-600" />
                                            </div>
                                            <div>
                                                <h4 className="font-medium text-slate-900 text-sm">题目生成</h4>
                                                <p className="text-xs text-slate-400">
                                                    {notebook.records.length > 0 || researchReport ? "生成练习题" : "需要笔记或研究报告"}
                                                </p>
                                            </div>
                                        </div>
                                    </button>

                                    {/* Smart Solver */}
                                    <button
                                        onClick={() => setStudioMode("solver")}
                                        className="w-full p-3 rounded-xl border border-slate-200 hover:border-blue-300 hover:bg-blue-50/50 transition-all text-left"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="w-9 h-9 rounded-lg bg-blue-100 flex items-center justify-center">
                                                <Calculator className="w-4 h-4 text-blue-600" />
                                            </div>
                                            <div>
                                                <h4 className="font-medium text-slate-900 text-sm">智能解题</h4>
                                                <p className="text-xs text-slate-400">解答问题</p>
                                            </div>
                                        </div>
                                    </button>

                                    {/* Guided Learning */}
                                    <button
                                        onClick={() => setStudioMode("guide")}
                                        disabled={notebook.records.length === 0}
                                        className="w-full p-3 rounded-xl border border-slate-200 hover:border-amber-300 hover:bg-amber-50/50 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="w-9 h-9 rounded-lg bg-amber-100 flex items-center justify-center">
                                                <GraduationCap className="w-4 h-4 text-amber-600" />
                                            </div>
                                            <div>
                                                <h4 className="font-medium text-slate-900 text-sm">引导学习</h4>
                                                <p className="text-xs text-slate-400">
                                                    {notebook.records.length > 0 ? "知识点学习" : "需要笔记记录"}
                                                </p>
                                            </div>
                                        </div>
                                    </button>

                                    {/* IdeaGen */}
                                    <button
                                        onClick={() => setStudioMode("ideagen")}
                                        disabled={notebook.records.length === 0}
                                        className="w-full p-3 rounded-xl border border-slate-200 hover:border-yellow-300 hover:bg-yellow-50/50 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="w-9 h-9 rounded-lg bg-yellow-100 flex items-center justify-center">
                                                <Lightbulb className="w-4 h-4 text-yellow-600" />
                                            </div>
                                            <div>
                                                <h4 className="font-medium text-slate-900 text-sm">创意生成</h4>
                                                <p className="text-xs text-slate-400">
                                                    {notebook.records.length > 0 ? "发现研究灵感" : "需要笔记记录"}
                                                </p>
                                            </div>
                                        </div>
                                    </button>
                                </div>
                            </div>

                            {/* Export Features */}
                            <div>
                                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                                    导出功能
                                </div>
                                <div className="mb-2">
                                    {renderExportSourceToggle()}
                                </div>
                                <div className="grid grid-cols-3 gap-2">
                                    {/* PDF Export */}
                                    <button
                                        onClick={handleExportPdf}
                                        disabled={!canExport || isExporting}
                                        className="p-3 rounded-xl border border-slate-200 hover:border-red-300 hover:bg-red-50/50 transition-all text-center disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <FileDown className="w-5 h-5 text-red-600 mx-auto mb-1" />
                                        <span className="text-xs text-slate-600">PDF</span>
                                    </button>

                                    {/* PPT Export */}
                                    <button
                                        onClick={handleExportPptx}
                                        disabled={!canExportPpt || isExporting}
                                        className="p-3 rounded-xl border border-slate-200 hover:border-orange-300 hover:bg-orange-50/50 transition-all text-center disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <Presentation className="w-5 h-5 text-orange-600 mx-auto mb-1" />
                                        <span className="text-xs text-slate-600">PPT</span>
                                    </button>

                                    {/* Mindmap */}
                                    <button
                                        onClick={handleGenerateMindmap}
                                        disabled={!canExport || isExporting}
                                        className="p-3 rounded-xl border border-slate-200 hover:border-purple-300 hover:bg-purple-50/50 transition-all text-center disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <GitBranch className="w-5 h-5 text-purple-600 mx-auto mb-1" />
                                        <span className="text-xs text-slate-600">思维导图</span>
                                    </button>
                                </div>
                                {!canExport && (
                                    <p className="text-xs text-slate-400 text-center mt-2">
                                        {exportContentSource === "research"
                                            ? "完成深度研究后可导出"
                                            : "选择来源后可导出"}
                                    </p>
                                )}
                                <div className="mt-3">
                                    {renderPptStylePanel()}
                                </div>
                            </div>

                            {/* My Notes List */}
                            <div>
                                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                                    我的笔记 ({notebook.records.length})
                                </div>
                                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                                    {notebook.records.length === 0 ? (
                                        <p className="text-xs text-slate-400 text-center py-4 border border-dashed border-slate-200 rounded-xl">
                                            暂无笔记，点击上方添加
                                        </p>
                                    ) : (
                                        notebook.records.slice().reverse().map((record) => (
                                            <div key={record.id} className="p-3 bg-white border border-slate-200 rounded-xl hover:border-blue-300 transition-all group">
                                                <div className="flex items-start justify-between mb-1">
                                                    <div className="font-medium text-sm text-slate-900 line-clamp-1" title={record.title}>
                                                        {record.title}
                                                    </div>
                                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); handleDownloadRecord(record); }}
                                                            className="p-1 text-slate-400 hover:text-blue-600 rounded"
                                                            title="下载"
                                                        >
                                                            <FileDown className="w-3.5 h-3.5" />
                                                        </button>
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); handleDeleteRecord(record.id); }}
                                                            className="p-1 text-slate-400 hover:text-red-600 rounded"
                                                            title="删除"
                                                        >
                                                            <Trash2 className="w-3.5 h-3.5" />
                                                        </button>
                                                    </div>
                                                </div>
                                                <p
                                                    className="text-xs text-slate-500 line-clamp-2 cursor-pointer hover:text-slate-700"
                                                    onClick={() => setSelectedRecord(record)}
                                                >
                                                    {record.output || record.user_query}
                                                </p>
                                                <div className="flex items-center gap-2 mt-2 text-[10px] text-slate-400">
                                                    <span className={`px-1.5 py-0.5 rounded ${record.type === "note" ? "bg-blue-50 text-blue-600" :
                                                        record.type === "solve" ? "bg-purple-50 text-purple-600" :
                                                            "bg-slate-50 text-slate-600"
                                                        }`}>
                                                        {record.type === "note" ? "笔记" :
                                                            record.type === "solve" ? "解题" :
                                                                record.type === "question" ? "题目" : "记录"}
                                                    </span>
                                                    <span>{new Date(record.created_at * 1000).toLocaleDateString()}</span>
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </div>
                        </div>
                    )}


                    {/* Research Mode */}
                    {
                        studioMode === "research" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-2">
                                        研究主题
                                    </label>
                                    <textarea
                                        value={researchTopic}
                                        onChange={(e) => setResearchTopic(e.target.value)}
                                        placeholder="输入你想研究的主题..."
                                        rows={3}
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none resize-none"
                                    />
                                </div>

                                <button
                                    onClick={() => startResearchWithTopic()}
                                    disabled={!researchTopic.trim() || researchRunning}
                                    className="w-full py-3 bg-emerald-600 text-white rounded-xl font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                >
                                    {researchRunning ? (
                                        <>
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                            研究中...
                                        </>
                                    ) : (
                                        <>
                                            <Microscope className="w-4 h-4" />
                                            开始研究
                                        </>
                                    )}
                                </button>

                                {/* Research Error Display */}
                                {researchError && (
                                    <div className="p-3 bg-red-50 border border-red-200 rounded-xl">
                                        <div className="flex items-center gap-2">
                                            <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
                                            <span className="text-red-600 text-sm flex-1">{researchError}</span>
                                        </div>
                                        <button
                                            onClick={() => setResearchError(null)}
                                            className="mt-2 text-xs text-red-500 hover:text-red-700 underline"
                                        >
                                            关闭
                                        </button>
                                    </div>
                                )}

                                {researchReport && (
                                    <div className="mt-4 p-4 bg-slate-50 rounded-xl">
                                        <div className="text-xs font-semibold text-slate-500 mb-2">
                                            研究结果预览
                                        </div>
                                        <div className="text-sm text-slate-700 line-clamp-6">
                                            {researchReport.slice(0, 300)}...
                                        </div>
                                    </div>
                                )}
                            </div>
                        )
                    }

                    {/* PDF Mode */}
                    {
                        studioMode === "pdf" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                <div className="text-center py-8">
                                    <FileDown className="w-12 h-12 text-red-300 mx-auto mb-4" />
                                    <p className="text-slate-700 font-medium mb-2">导出为 PDF</p>
                                    <p className="text-sm text-slate-400 mb-6">
                                        将当前内容导出为 PDF 文档
                                    </p>
                                    <div className="mb-4">
                                        {renderExportSourceToggle()}
                                    </div>
                                    <button
                                        onClick={handleExportPdf}
                                        disabled={!canExport || isExporting}
                                        className="px-6 py-3 bg-red-600 text-white rounded-xl font-medium hover:bg-red-700 disabled:opacity-50"
                                    >
                                        {isExporting ? "导出中..." : "导出 PDF"}
                                    </button>
                                    {!canExport && (
                                        <p className="text-xs text-slate-400 mt-3">
                                            {exportContentSource === "research"
                                                ? "完成深度研究后可导出"
                                                : "选择来源后可导出"}
                                        </p>
                                    )}
                                </div>
                            </div>
                        )
                    }

                    {/* PPT Mode */}
                    {
                        studioMode === "ppt" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                <div className="text-center py-8">
                                    <Presentation className="w-12 h-12 text-orange-300 mx-auto mb-4" />
                                    <p className="text-slate-700 font-medium mb-2">导出为 PPT</p>
                                    <p className="text-sm text-slate-400 mb-6">
                                        将当前内容转换为演示文稿
                                    </p>
                                    <div className="mb-4">
                                        {renderExportSourceToggle()}
                                    </div>
                                    <div className="mb-4">
                                        {renderPptStylePanel()}
                                    </div>
                                    <button
                                        onClick={handleExportPptx}
                                        disabled={!canExportPpt || isExporting}
                                        className="px-6 py-3 bg-orange-600 text-white rounded-xl font-medium hover:bg-orange-700 disabled:opacity-50"
                                    >
                                        {isExporting ? "导出中..." : "导出 PPT"}
                                    </button>
                                    {!canExportPpt && (
                                        <p className="text-xs text-slate-400 mt-3">
                                            {!canExport
                                                ? (exportContentSource === "research"
                                                    ? "完成深度研究后可导出"
                                                    : "选择来源后可导出")
                                                : (!canUsePresetStyle
                                                    ? "请选择预设风格"
                                                    : (!canUseSourceStyle
                                                        ? "选择来源后可生成风格"
                                                        : "请选择 PPT 模板"))}
                                        </p>
                                    )}
                                </div>
                            </div>
                        )
                    }

                    {/* Mindmap Mode */}
                    {
                        studioMode === "mindmap" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                {!mindmapCode ? (
                                    <div className="text-center py-8">
                                        <GitBranch className="w-12 h-12 text-purple-300 mx-auto mb-4" />
                                        <p className="text-slate-700 font-medium mb-2">生成思维导图</p>
                                        <p className="text-sm text-slate-400 mb-6">
                                            将内容结构可视化
                                        </p>
                                        <div className="mb-4">
                                            {renderExportSourceToggle()}
                                        </div>
                                        <button
                                            onClick={handleGenerateMindmap}
                                            disabled={!canExport || isExporting}
                                            className="px-6 py-3 bg-purple-600 text-white rounded-xl font-medium hover:bg-purple-700 disabled:opacity-50"
                                        >
                                            {isExporting ? "生成中..." : "生成思维导图"}
                                        </button>
                                        {!canExport && (
                                            <p className="text-xs text-slate-400 mt-3">
                                                {exportContentSource === "research"
                                                    ? "完成深度研究后可导出"
                                                    : "选择来源后可导出"}
                                            </p>
                                        )}
                                    </div>
                                ) : (
                                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                                        <Mermaid chart={mindmapCode} />
                                    </div>
                                )}
                            </div>
                        )
                    }

                    {/* Question Generator Mode */}
                    {
                        studioMode === "question" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                <div className="text-center py-8">
                                    <PenTool className="w-12 h-12 text-purple-300 mx-auto mb-4" />
                                    <p className="text-slate-700 font-medium mb-2">题目生成</p>
                                    <p className="text-sm text-slate-400 mb-4">
                                        基于笔记内容生成练习题
                                    </p>
                                    <a
                                        href="/question"
                                        target="_blank"
                                        className="inline-block px-6 py-3 bg-purple-600 text-white rounded-xl font-medium hover:bg-purple-700 transition-colors"
                                    >
                                        打开题目生成器
                                    </a>
                                </div>
                            </div>
                        )
                    }

                    {/* Smart Solver Mode */}
                    {
                        studioMode === "solver" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                <div className="text-center py-8">
                                    <Calculator className="w-12 h-12 text-blue-300 mx-auto mb-4" />
                                    <p className="text-slate-700 font-medium mb-2">智能解题</p>
                                    <p className="text-sm text-slate-400 mb-4">
                                        使用 AI 解答问题
                                    </p>
                                    <a
                                        href="/solver"
                                        target="_blank"
                                        className="inline-block px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
                                    >
                                        打开智能解题器
                                    </a>
                                </div>
                            </div>
                        )
                    }

                    {/* Guided Learning Mode */}
                    {
                        studioMode === "guide" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                <div className="text-center py-8">
                                    <GraduationCap className="w-12 h-12 text-amber-300 mx-auto mb-4" />
                                    <p className="text-slate-700 font-medium mb-2">引导学习</p>
                                    <p className="text-sm text-slate-400 mb-4">
                                        基于笔记记录进行知识点学习
                                    </p>
                                    <a
                                        href="/guide"
                                        target="_blank"
                                        className="inline-block px-6 py-3 bg-amber-600 text-white rounded-xl font-medium hover:bg-amber-700 transition-colors"
                                    >
                                        打开引导学习
                                    </a>
                                </div>
                            </div>
                        )
                    }

                    {/* IdeaGen Mode */}
                    {
                        studioMode === "ideagen" && (
                            <div className="space-y-4">
                                <button
                                    onClick={() => setStudioMode("idle")}
                                    className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                    返回
                                </button>

                                <div className="text-center py-8">
                                    <Lightbulb className="w-12 h-12 text-yellow-300 mx-auto mb-4" />
                                    <p className="text-slate-700 font-medium mb-2">创意生成</p>
                                    <p className="text-sm text-slate-400 mb-4">
                                        从笔记中发现研究灵感
                                    </p>
                                    <a
                                        href="/ideagen"
                                        target="_blank"
                                        className="inline-block px-6 py-3 bg-yellow-600 text-white rounded-xl font-medium hover:bg-yellow-700 transition-colors"
                                    >
                                        打开创意生成器
                                    </a>
                                </div>
                            </div>
                        )
                    }
                </div >

                {/* Collapse Button */}
                < button
                    onClick={() => setRightCollapsed(true)}
                    className="p-2 border-t border-slate-200 text-slate-400 hover:bg-slate-50 flex items-center justify-center"
                >
                    <ChevronRight className="w-4 h-4" />
                </button >
            </div >

            {/* Right Expand Button */}
            {
                rightCollapsed && (
                    <button
                        onClick={() => setRightCollapsed(false)}
                        className="w-8 bg-white border-l border-slate-200 flex items-center justify-center text-slate-400 hover:bg-slate-50"
                    >
                        <ChevronLeft className="w-4 h-4" />
                    </button>
                )
            }

            {/* Add Source Modal */}
            {
                showAddSourceModal && (
                    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                        <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl">
                            <h3 className="text-lg font-semibold text-slate-900 mb-4">添加来源</h3>

                            <div className="space-y-4">
                                {/* URL Input */}
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">
                                        网址 URL
                                    </label>
                                    <input
                                        type="text"
                                        value={sourceUrl}
                                        onChange={(e) => setSourceUrl(e.target.value)}
                                        placeholder="https://example.com"
                                        className="w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                                    />
                                </div>

                                {/* KB Selection */}
                                {kbs.length > 0 && (
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            或选择知识库
                                        </label>
                                        <select
                                            value={selectedKb}
                                            onChange={(e) => {
                                                setSelectedKb(e.target.value);
                                                if (e.target.value) {
                                                    const newSource: Source = {
                                                        id: `kb-${Date.now()}`,
                                                        type: "kb",
                                                        title: e.target.value,
                                                        selected: true,
                                                    };
                                                    setSources(prev => [...prev, newSource]);
                                                }
                                            }}
                                            className="w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                                        >
                                            <option value="">选择知识库...</option>
                                            {kbs.map((kb) => (
                                                <option key={kb.name} value={kb.name}>
                                                    {kb.name}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                )}
                            </div>

                            <div className="flex gap-3 mt-6">
                                <button
                                    onClick={() => {
                                        setShowAddSourceModal(false);
                                        setSourceUrl("");
                                    }}
                                    className="flex-1 px-4 py-2 border border-slate-200 rounded-lg text-slate-700 hover:bg-slate-50"
                                >
                                    取消
                                </button>
                                <button
                                    onClick={handleAddSourceUrl}
                                    disabled={!sourceUrl.trim()}
                                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                                >
                                    添加
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Add Note Modal */}
            {
                showAddNoteModal && (
                    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                        <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-xl">
                            <h3 className="text-lg font-semibold text-slate-900 mb-4">添加笔记</h3>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">
                                        标题
                                    </label>
                                    <input
                                        type="text"
                                        value={noteTitle}
                                        onChange={(e) => setNoteTitle(e.target.value)}
                                        placeholder="笔记标题"
                                        className="w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">
                                        内容
                                    </label>
                                    <textarea
                                        value={noteContent}
                                        onChange={(e) => setNoteContent(e.target.value)}
                                        placeholder="输入笔记内容..."
                                        rows={6}
                                        className="w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
                                    />
                                </div>
                            </div>

                            <div className="flex gap-3 mt-6">
                                <button
                                    onClick={() => {
                                        setShowAddNoteModal(false);
                                        setNoteTitle("");
                                        setNoteContent("");
                                    }}
                                    className="flex-1 px-4 py-2 border border-slate-200 rounded-lg text-slate-700 hover:bg-slate-50"
                                >
                                    取消
                                </button>
                                <button
                                    onClick={handleAddNote}
                                    disabled={!noteTitle.trim() || !noteContent.trim()}
                                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                                >
                                    保存笔记
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }
            {/* Selected Record Preview Modal */}
            {selectedRecord && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setSelectedRecord(null)}>
                    <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl animate-in zoom-in-95" onClick={(e) => e.stopPropagation()}>
                        <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-blue-50 to-indigo-50 rounded-t-2xl">
                            <h3 className="font-bold text-lg text-slate-900 truncate flex-1">{selectedRecord.title}</h3>
                            <button onClick={() => setSelectedRecord(null)} className="p-1.5 hover:bg-white/50 rounded-lg transition-colors ml-2">
                                <X className="w-5 h-5 text-slate-500" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 prose prose-slate max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                                {processLatexContent(selectedRecord.output || selectedRecord.user_query)}
                            </ReactMarkdown>
                        </div>
                        <div className="p-4 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex justify-end gap-2">
                            <button
                                onClick={() => handleDownloadRecord(selectedRecord)}
                                className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-xl hover:bg-slate-50 flex items-center gap-2 text-sm"
                            >
                                <FileDown className="w-4 h-4" />
                                下载
                            </button>
                            <button
                                onClick={() => setSelectedRecord(null)}
                                className="px-4 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm"
                            >
                                关闭
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div >
    );
}
