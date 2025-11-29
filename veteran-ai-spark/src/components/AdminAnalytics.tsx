import { useEffect, useState, Suspense } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { ArrowLeft, RefreshCw, Users, MessageSquare, Eye, TrendingUp, Globe, BarChart3, Calendar, Link, Cpu, Zap, Clock, Hash, CheckCircle, XCircle, AlertCircle, MapPin, Activity, Database, Shield, Lock, Download, Trash2, AlertTriangle } from "lucide-react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { useToast } from "@/hooks/use-toast";
import USHeatMap from "@/components/USHeatMap";

interface TimelineEntry {
  id: number;
  timestamp: string;
  question: string;
  question_hash: string;
  cache_mode: string;
  semantic_similarity?: number;
  answer_preview: string;
  full_answer?: string;
  citations_count: number;
  token_usage: {
    model_big?: string;
    model_small?: string;
    tokens_big?: number;
    tokens_small?: number;
    total_tokens?: number;
  };
  latency_ms: number;
  retrieved_docs: number;
  compressed_tokens: number;
  final_tokens: number;
  user_ip: string;
  error_message: string;
  created_at: string;
}

interface TimelineData {
  status: string;
  entries: TimelineEntry[];
  stats: {
    total_questions: number;
    exact_hits: number;
    semantic_hits: number;
    cache_misses: number;
    cache_hit_rate: number;
    avg_latency: number;
    total_tokens_used: number;
    avg_similarity: number;
    hourly_breakdown: Array<{
      hour: string;
      questions: number;
      hits: number;
    }>;
  };
  pagination: {
    limit: number;
    offset: number;
    total_returned: number;
  };
}

const TimelineView = () => {
  const [timelineData, setTimelineData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [selectedQuestion, setSelectedQuestion] = useState<TimelineEntry | null>(null);
  const { toast } = useToast();

  const fetchTimeline = async (cacheMode?: string) => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        limit: '50',
        offset: '0'
      });
      
      if (cacheMode && cacheMode !== 'all') {
        params.append('cache_mode', cacheMode);
      }

      const response = await fetch(`/api/analytics/timeline?${params}`, {
        headers: {
          'X-Admin-Token': 'flip_ruby'
        }
      });
      if (!response.ok) throw new Error('Failed to fetch timeline');
      
      const data = await response.json();
      setTimelineData(data);
    } catch (error) {
      console.error('Timeline fetch error:', error);
      toast({
        title: "Error",
        description: "Failed to load timeline data",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTimeline(filter === 'all' ? undefined : filter);
  }, [filter]);

  const getCacheModeIcon = (mode: string) => {
    switch (mode) {
      case 'exact_hit':
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case 'semantic_hit':
        return <CheckCircle className="h-4 w-4 text-blue-600" />;
      case 'miss':
        return <XCircle className="h-4 w-4 text-red-600" />;
      default:
        return <AlertCircle className="h-4 w-4 text-gray-600" />;
    }
  };

  const getCacheModeBadge = (mode: string) => {
    switch (mode) {
      case 'exact_hit':
        return <Badge variant="default" className="bg-green-100 text-green-800">Exact Hit</Badge>;
      case 'semantic_hit':
        return <Badge variant="default" className="bg-blue-100 text-blue-800">Semantic Hit</Badge>;
      case 'miss':
        return <Badge variant="destructive">Cache Miss</Badge>;
      default:
        return <Badge variant="secondary">Unknown</Badge>;
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  const formatTokens = (tokens: number) => {
    return tokens?.toLocaleString() || '0';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <RefreshCw className="h-6 w-6 animate-spin mr-2" />
        Loading timeline...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Timeline Stats */}
      {timelineData?.stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="bg-slate-800/50 border-slate-700">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Questions</CardTitle>
              <MessageSquare className="h-4 w-4 text-orange-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-500">{timelineData.stats.total_questions}</div>
              <p className="text-xs text-muted-foreground">Last 24 hours</p>
            </CardContent>
          </Card>

          <Card className="bg-slate-800/50 border-slate-700">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Cache Hit Rate</CardTitle>
              <Zap className="h-4 w-4 text-orange-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-500">
                {timelineData.stats.cache_hit_rate?.toFixed(1) || 0}%
              </div>
              <p className="text-xs text-muted-foreground">
                {(timelineData.stats.exact_hits || 0) + (timelineData.stats.semantic_hits || 0)} hits
              </p>
            </CardContent>
          </Card>

          <Card className="bg-slate-800/50 border-slate-700">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Avg Latency</CardTitle>
              <Clock className="h-4 w-4 text-orange-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-500">
                {Math.round(timelineData.stats.avg_latency || 0)}ms
              </div>
              <p className="text-xs text-muted-foreground">Response time</p>
            </CardContent>
          </Card>

          <Card className="bg-slate-800/50 border-slate-700">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Tokens Used</CardTitle>
              <Hash className="h-4 w-4 text-orange-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-500">
                {formatTokens(timelineData.stats.total_tokens_used)}
              </div>
              <p className="text-xs text-muted-foreground">Total consumption</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card className="bg-gray-800/50 border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-200">Question Timeline</CardTitle>
          <CardDescription className="text-gray-400">
            Comprehensive view of all questions, cache performance, and token usage
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 mb-4">
            <Button
              size="sm"
              onClick={() => setFilter('all')}
              className={filter === 'all' 
                ? 'bg-orange-600 hover:bg-orange-700 text-white' 
                : 'bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600'}
            >
              All Questions
            </Button>
            <Button
              size="sm"
              onClick={() => setFilter('exact_hit')}
              className={filter === 'exact_hit' 
                ? 'bg-orange-600 hover:bg-orange-700 text-white' 
                : 'bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600'}
            >
              Exact Hits
            </Button>
            <Button
              size="sm"
              onClick={() => setFilter('semantic_hit')}
              className={filter === 'semantic_hit' 
                ? 'bg-orange-600 hover:bg-orange-700 text-white' 
                : 'bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600'}
            >
              Semantic Hits
            </Button>
            <Button
              size="sm"
              onClick={() => setFilter('miss')}
              className={filter === 'miss' 
                ? 'bg-orange-600 hover:bg-orange-700 text-white' 
                : 'bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600'}
            >
              Cache Misses
            </Button>
          </div>

          {/* Timeline Table */}
          <div className="rounded-md border border-gray-700">
            <Table>
              <TableHeader>
                <TableRow className="border-gray-700">
                  <TableHead className="text-gray-400">Timestamp</TableHead>
                  <TableHead className="text-gray-400">Question</TableHead>
                  <TableHead className="text-gray-400">Cache Mode</TableHead>
                  <TableHead className="text-gray-400">Similarity</TableHead>
                  <TableHead className="text-gray-400">Latency</TableHead>
                  <TableHead className="text-gray-400">Tokens</TableHead>
                  <TableHead className="text-gray-400">Citations</TableHead>
                  <TableHead className="text-gray-400">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {timelineData?.entries?.map((entry) => (
                  <TableRow key={entry.id} className="border-gray-700">
                    <TableCell className="text-sm text-gray-300">
                      {formatTimestamp(entry.timestamp)}
                    </TableCell>
                    <TableCell className="max-w-md">
                      <div className="truncate text-gray-300" title={entry.question}>
                        {entry.question}
                      </div>
                      {entry.answer_preview && (
                        <div className="text-xs text-gray-500 mt-1 truncate">
                          {entry.answer_preview}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getCacheModeIcon(entry.cache_mode)}
                        {getCacheModeBadge(entry.cache_mode)}
                      </div>
                    </TableCell>
                    <TableCell>
                      {entry.semantic_similarity ? (
                        <Badge className="bg-gray-700 text-orange-500 border-gray-600">
                          {(entry.semantic_similarity * 100).toFixed(1)}%
                        </Badge>
                      ) : (
                        <span className="text-gray-500">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge className="bg-gray-700 text-orange-500 border-gray-600 text-xs">
                        {entry.latency_ms}ms
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        <div className="font-medium text-orange-500">
                          {formatTokens(entry.token_usage?.total_tokens || 0)}
                        </div>
                        {entry.token_usage?.tokens_big && (
                          <div className="text-xs text-gray-500">
                            Big: {formatTokens(entry.token_usage.tokens_big)}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge className="bg-gray-700 text-orange-500 border-gray-600">
                        {entry.citations_count}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        onClick={() => setSelectedQuestion(entry)}
                        className="bg-gray-700 hover:bg-gray-600 text-gray-300"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {(!timelineData?.entries || timelineData.entries.length === 0) && (
            <div className="text-center py-8 text-gray-500">
              No questions found for the selected filter.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Question Details Modal/Dialog */}
      {selectedQuestion && (
        <Card className="mt-4 bg-slate-700/50 border-slate-600">
          <CardHeader className="relative">
            <div className="flex items-center justify-between">
              <CardTitle className="text-orange-500">Question Details</CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const data = {
                      question: selectedQuestion.question,
                      answer: selectedQuestion.full_answer || selectedQuestion.answer_preview,
                      cache_mode: selectedQuestion.cache_mode,
                      latency_ms: selectedQuestion.latency_ms,
                      token_usage: selectedQuestion.token_usage,
                      citations_count: selectedQuestion.citations_count,
                      timestamp: selectedQuestion.timestamp,
                      user_ip: selectedQuestion.user_ip
                    };
                    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `question-${selectedQuestion.id}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                    toast({
                      title: "Downloaded",
                      description: "Question data exported successfully"
                    });
                  }}
                  className="border-orange-500/50 text-orange-500 hover:bg-orange-500/10"
                >
                  <Download className="h-4 w-4 mr-1" />
                  Download
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    if (!window.confirm('Are you sure you want to delete this question data?')) return;
                    try {
                      const response = await fetch(`/api/analytics/timeline/${selectedQuestion.id}`, {
                        method: 'DELETE',
                        headers: {
                          'X-Admin-Token': new URLSearchParams(window.location.search).get('token') || ''
                        }
                      });
                      if (response.ok) {
                        toast({
                          title: "Deleted",
                          description: "Question data deleted successfully"
                        });
                        setSelectedQuestion(null);
                        fetchTimeline(filter === 'all' ? undefined : filter);
                      } else {
                        throw new Error('Delete failed');
                      }
                    } catch (error) {
                      toast({
                        title: "Error",
                        description: "Failed to delete question data",
                        variant: "destructive"
                      });
                    }
                  }}
                  className="border-red-500/50 text-red-500 hover:bg-red-500/10"
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  Delete
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedQuestion(null)}
                  className="text-slate-400 hover:text-white"
                >
                  ✕
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="bg-slate-800/50 rounded-lg p-4">
              <label className="font-medium text-orange-500 block mb-2">Question:</label>
              <p className="text-white">{selectedQuestion.question}</p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-4">
              <label className="font-medium text-orange-500 block mb-2">Full Answer:</label>
              <p className="text-slate-300 whitespace-pre-wrap max-h-96 overflow-y-auto">
                {selectedQuestion.full_answer || selectedQuestion.answer_preview || 'No answer available'}
              </p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-800/50 rounded-lg p-3">
                <label className="font-medium text-orange-500 text-sm block mb-1">Cache Mode</label>
                <div className="mt-1">{getCacheModeBadge(selectedQuestion.cache_mode)}</div>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <label className="font-medium text-orange-500 text-sm block mb-1">Latency</label>
                <p className="text-white font-semibold">{selectedQuestion.latency_ms}ms</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <label className="font-medium text-orange-500 text-sm block mb-1">Citations</label>
                <p className="text-white font-semibold">{selectedQuestion.citations_count}</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-3">
                <label className="font-medium text-orange-500 text-sm block mb-1">User IP</label>
                <p className="text-white font-mono text-sm">{selectedQuestion.user_ip}</p>
              </div>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-4">
              <label className="font-medium text-orange-500 block mb-2">Token Usage:</label>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-slate-400">Total:</span>
                  <span className="text-white ml-2 font-semibold">{formatTokens(selectedQuestion.token_usage?.total_tokens || 0)}</span>
                </div>
                {selectedQuestion.token_usage?.tokens_big && (
                  <div>
                    <span className="text-slate-400">Big Model:</span>
                    <span className="text-white ml-2 font-semibold">{formatTokens(selectedQuestion.token_usage.tokens_big)}</span>
                  </div>
                )}
                {selectedQuestion.token_usage?.tokens_small && (
                  <div>
                    <span className="text-slate-400">Small Model:</span>
                    <span className="text-white ml-2 font-semibold">{formatTokens(selectedQuestion.token_usage.tokens_small)}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="text-xs text-slate-500">
              Timestamp: {formatTimestamp(selectedQuestion.timestamp)} | ID: {selectedQuestion.id}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// Cache Metrics Tab Component
interface CacheMetrics {
  exact_hits: number;
  exact_misses: number;
  semantic_hits: number;
  semantic_misses: number;
  db_hits: number;
  db_writes: number;
  db_errors: number;
  total_hits: number;
  hit_rate: string;
  memory_cache_size: number;
  semantic_cache_size: number;
  database_cache_size: number;
  database_available: boolean;
  max_memory_entries: number;
  max_db_entries: number;
  ttl_hours: number;
}

const CacheMetricsTab = ({ adminToken }: { adminToken: string | null }) => {
  const [cacheMetrics, setCacheMetrics] = useState<CacheMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const fetchCacheMetrics = async () => {
    try {
      const response = await fetch('/cache/metrics', {
        headers: adminToken ? { 'X-Admin-Token': adminToken } : {}
      });
      if (response.ok) {
        const data = await response.json();
        setCacheMetrics(data);
      }
    } catch (error) {
      console.error('Failed to fetch cache metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleClearCache = async () => {
    if (!adminToken) {
      toast({ title: "Error", description: "Admin token required", variant: "destructive" });
      return;
    }
    
    try {
      const response = await fetch('/cache/clear', {
        method: 'POST',
        headers: { 'X-Admin-Token': adminToken }
      });
      
      if (response.ok) {
        toast({ title: "Success", description: "Cache cleared successfully" });
        fetchCacheMetrics();
      } else {
        toast({ title: "Error", description: "Failed to clear cache", variant: "destructive" });
      }
    } catch (error) {
      toast({ title: "Error", description: "Failed to clear cache", variant: "destructive" });
    }
  };

  useEffect(() => {
    fetchCacheMetrics();
    const interval = setInterval(fetchCacheMetrics, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <TabsContent value="cache" className="space-y-6">
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin mr-2" />
          Loading cache metrics...
        </div>
      </TabsContent>
    );
  }

  return (
    <TabsContent value="cache" className="space-y-6">
      {/* Cache Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="bg-gray-800/50 border-gray-700">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-gray-300">Cache Hit Rate</CardTitle>
            <Zap className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-500">
              {cacheMetrics?.hit_rate || '0%'}
            </div>
            <p className="text-xs text-gray-400">
              {cacheMetrics?.total_hits || 0} total hits
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gray-800/50 border-gray-700">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-gray-300">Exact Hits</CardTitle>
            <CheckCircle className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-500">
              {cacheMetrics?.exact_hits || 0}
            </div>
            <p className="text-xs text-gray-400">
              {cacheMetrics?.exact_misses || 0} misses
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gray-800/50 border-gray-700">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-gray-300">Semantic Hits</CardTitle>
            <Activity className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-500">
              {cacheMetrics?.semantic_hits || 0}
            </div>
            <p className="text-xs text-gray-400">
              {cacheMetrics?.semantic_misses || 0} misses
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gray-800/50 border-gray-700">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-gray-300">Database Hits</CardTitle>
            <Database className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-500">
              {cacheMetrics?.db_hits || 0}
            </div>
            <p className="text-xs text-gray-400">
              {cacheMetrics?.db_writes || 0} writes, {cacheMetrics?.db_errors || 0} errors
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Cache Storage Details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-gray-800/50 border-gray-700">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2 text-gray-200">
              <Database className="h-5 w-5 text-orange-500" />
              <span>Cache Storage</span>
            </CardTitle>
            <CardDescription className="text-gray-400">Memory and database cache utilization</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="font-medium text-gray-300">Memory Cache (L1)</span>
                <Badge className="bg-gray-700 text-orange-500 border-gray-600">
                  {cacheMetrics?.memory_cache_size || 0} / {cacheMetrics?.max_memory_entries || 1000} entries
                </Badge>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div 
                  className="bg-orange-500 h-2 rounded-full transition-all" 
                  style={{ width: `${Math.min(((cacheMetrics?.memory_cache_size || 0) / (cacheMetrics?.max_memory_entries || 1000)) * 100, 100)}%` }}
                />
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="font-medium text-gray-300">Semantic Entries</span>
                <Badge className="bg-gray-700 text-orange-500 border-gray-600">
                  {cacheMetrics?.semantic_cache_size || 0} entries
                </Badge>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div 
                  className="bg-orange-400 h-2 rounded-full transition-all" 
                  style={{ width: `${Math.min(((cacheMetrics?.semantic_cache_size || 0) / (cacheMetrics?.max_memory_entries || 1000)) * 100, 100)}%` }}
                />
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="font-medium text-gray-300">Database Cache (L2)</span>
                <Badge className={cacheMetrics?.database_available 
                  ? "bg-orange-600 text-white" 
                  : "bg-gray-700 text-gray-400 border-gray-600"}>
                  {cacheMetrics?.database_available ? `${cacheMetrics?.database_cache_size || 0} entries` : 'Unavailable'}
                </Badge>
              </div>
              {cacheMetrics?.database_available && (
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div 
                    className="bg-orange-600 h-2 rounded-full transition-all" 
                    style={{ width: `${Math.min(((cacheMetrics?.database_cache_size || 0) / (cacheMetrics?.max_db_entries || 10000)) * 100, 100)}%` }}
                  />
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gray-800/50 border-gray-700">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2 text-gray-200">
              <Clock className="h-5 w-5 text-orange-500" />
              <span>Cache Configuration</span>
            </CardTitle>
            <CardDescription className="text-gray-400">Current cache settings and actions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="font-medium text-gray-300">TTL (Time to Live)</span>
              <Badge className="bg-gray-700 text-orange-500 border-gray-600">{cacheMetrics?.ttl_hours || 24} hours</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-medium text-gray-300">Max Memory Entries</span>
              <Badge className="bg-gray-700 text-orange-500 border-gray-600">{cacheMetrics?.max_memory_entries || 1000}</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-medium text-gray-300">Max Database Entries</span>
              <Badge className="bg-gray-700 text-orange-500 border-gray-600">{cacheMetrics?.max_db_entries || 10000}</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-medium text-gray-300">Database Available</span>
              <Badge className={cacheMetrics?.database_available 
                ? "bg-orange-600 text-white" 
                : "bg-red-900 text-red-200"}>
                {cacheMetrics?.database_available ? 'Yes' : 'No'}
              </Badge>
            </div>
            
            <div className="pt-4 border-t border-gray-700">
              <Button 
                className="w-full bg-red-900 hover:bg-red-800 text-red-200"
                onClick={handleClearCache}
              >
                <XCircle className="h-4 w-4 mr-2" />
                Clear All Caches
              </Button>
              <p className="text-xs text-gray-500 mt-2 text-center">
                This will clear both memory and database caches
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Cache Performance Insights */}
      <Card className="bg-gray-800/50 border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-200">Cache Performance Insights</CardTitle>
          <CardDescription className="text-gray-400">Understanding your cache efficiency</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center p-4 bg-gray-700/50 rounded-lg">
              <div className="text-2xl font-bold text-orange-500">
                {cacheMetrics?.exact_hits || 0}
              </div>
              <p className="text-sm text-gray-300">Exact Query Matches</p>
              <p className="text-xs text-gray-500 mt-1">Fastest response time</p>
            </div>
            <div className="text-center p-4 bg-gray-700/50 rounded-lg">
              <div className="text-2xl font-bold text-orange-500">
                {cacheMetrics?.semantic_hits || 0}
              </div>
              <p className="text-sm text-gray-300">Semantic Matches</p>
              <p className="text-xs text-gray-500 mt-1">Similar question detection</p>
            </div>
            <div className="text-center p-4 bg-gray-700/50 rounded-lg">
              <div className="text-2xl font-bold text-orange-500">
                {cacheMetrics?.db_hits || 0}
              </div>
              <p className="text-sm text-gray-300">Database Cache Hits</p>
              <p className="text-xs text-gray-500 mt-1">Persisted responses</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </TabsContent>
  );
};

interface AnalyticsData {
  totals: {
    pageviews: number;
    uniques: number;
    chat_questions: number;
    ask_count: number;
    visit_count: number;
    unique_visitors: number;
  };
  by_day: Array<{
    day: string;
    pageviews: number;
    chat_questions: number;
    uniques: number;
  }>;
  top_pages: Array<{
    path: string;
    pageviews: number;
  }>;
  top_referrers: Array<{
    referrer: string;
    visits: number;
  }>;
  visitor_locations: {
    us_states: Record<string, number>;
    international: number;
    local: number;
    unknown: number;
    total_tracked: number;
    raw_data: Record<string, number>;
  };
  service_info: {
    first_visit: string | null;
    last_updated: string;
    engagement_rate: number;
    questions_per_user: number;
  };
  token_usage: any;
  performance?: {
    available: boolean;
    summary?: {
      total_chats: number;
      avg_ms: number;
      p95_ms: number;
      success_rate: number;
      avg_answer_chars: number;
      avg_prompt_chars: number;
    };
    by_provider?: Array<{
      provider: string;
      queries: number;
      avg_ms: number;
      p95_ms: number;
      success_rate: number;
      avg_answer_chars: number;
    }>;
    daily?: Array<{
      day: string;
      avg_ms: number;
      p95_ms: number;
      queries: number;
    }>;
    message?: string;
    error?: string;
  };
}

const AdminAnalytics = () => {
  const [searchParams] = useSearchParams();
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const { toast } = useToast();

  // Check for admin token
  const adminToken = searchParams.get('token');
  const isAuthenticated = Boolean(adminToken);

  const fetchAnalytics = async () => {
    if (!adminToken) {
      setError("Admin token required");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`/api/analytics/stats?days=${days}`, {
        headers: {
          'X-Admin-Token': adminToken
        }
      });
      
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Invalid admin token");
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      setAnalytics(data);
      setError(null);
    } catch (err) {
      console.error('Error fetching analytics:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch analytics');
      toast({
        title: "Error",
        description: "Failed to fetch analytics data. Please check your admin token.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
    
    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchAnalytics, 60000);
    
    return () => clearInterval(interval);
  }, [days, adminToken]);

  const handleRefresh = () => {
    setLoading(true);
    fetchAnalytics();
  };

  const formatDate = (isoString: string | null) => {
    if (!isoString) return 'Unknown';
    try {
      return new Date(isoString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return 'Unknown';
    }
  };

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat().format(num || 0);
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <Card className="w-full max-w-md mx-4 border-slate-700 bg-slate-800/50 backdrop-blur">
          <CardHeader className="text-center space-y-4">
            <div className="mx-auto w-16 h-16 bg-gradient-to-br from-amber-500 to-orange-600 rounded-full flex items-center justify-center">
              <Shield className="h-8 w-8 text-white" />
            </div>
            <CardTitle className="text-2xl text-white">Admin Access Required</CardTitle>
            <CardDescription className="text-slate-400">
              This dashboard requires authentication to access sensitive analytics data.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Lock className="h-4 w-4" />
                <span>Access URL format:</span>
              </div>
              <code className="block p-3 bg-slate-900/50 rounded-lg text-amber-400 text-sm font-mono">
                /admin/analytics?token=YOUR_TOKEN
              </code>
            </div>
            <div className="pt-4 border-t border-slate-700">
              <Button asChild variant="outline" className="w-full border-slate-600 hover:bg-slate-700">
                <RouterLink to="/">
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Back to Home
                </RouterLink>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loading && !analytics) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background">
        <div className="flex items-center space-x-2">
          <RefreshCw className="h-6 w-6 animate-spin" />
          <span className="text-lg">Loading analytics...</span>
        </div>
      </div>
    );
  }

  if (error && !analytics) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold text-destructive">Error Loading Analytics</h1>
          <p className="text-muted-foreground">{error}</p>
          <Button onClick={handleRefresh} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Try Again
          </Button>
          <div className="mt-4">
            <Button asChild variant="ghost">
              <RouterLink to="/">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to Home
              </RouterLink>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-black text-gray-100">
      {/* Top Navigation Bar */}
      <div className="sticky top-0 z-50 w-full border-b border-gray-800 bg-gray-950/95 backdrop-blur">
        <div className="max-w-7xl mx-auto flex h-16 items-center justify-between px-4">
          <div className="flex items-center gap-4">
            <Button asChild variant="ghost" size="sm" className="bg-gray-800 hover:bg-gray-700 text-gray-200 border-gray-700">
              <RouterLink to="/">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Home
              </RouterLink>
            </Button>
            <div className="hidden md:flex items-center gap-2 pl-4 border-l border-gray-700">
              <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
                <BarChart3 className="h-4 w-4 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-white">Admin Analytics</h1>
                <p className="text-xs text-gray-400">Veterans Benefits AI</p>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-9 px-3 text-sm border border-gray-700 rounded-md bg-gray-800 text-gray-200 focus:outline-none focus:ring-2 focus:ring-orange-500"
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last year</option>
            </select>
            <Button onClick={handleRefresh} size="sm" disabled={loading} className="bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Badge className="bg-orange-600 text-white border-0">
              <Shield className="h-3 w-3 mr-1" />
              Admin
            </Badge>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto py-8 px-4">

        {analytics && (
          <Tabs defaultValue="overview" className="space-y-6">
            <TabsList className="grid w-full grid-cols-8 h-12 bg-gray-800 border border-gray-700">
              <TabsTrigger value="overview" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <BarChart3 className="h-4 w-4" />
                <span className="hidden sm:inline">Overview</span>
              </TabsTrigger>
              <TabsTrigger value="locations" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <MapPin className="h-4 w-4" />
                <span className="hidden sm:inline">Locations</span>
              </TabsTrigger>
              <TabsTrigger value="traffic" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <Activity className="h-4 w-4" />
                <span className="hidden sm:inline">Traffic</span>
              </TabsTrigger>
              <TabsTrigger value="tokens" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <Zap className="h-4 w-4" />
                <span className="hidden sm:inline">Tokens</span>
              </TabsTrigger>
              <TabsTrigger value="performance" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <TrendingUp className="h-4 w-4" />
                <span className="hidden sm:inline">Performance</span>
              </TabsTrigger>
              <TabsTrigger value="cache" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <Database className="h-4 w-4" />
                <span className="hidden sm:inline">Cache</span>
              </TabsTrigger>
              <TabsTrigger value="timeline" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <Calendar className="h-4 w-4" />
                <span className="hidden sm:inline">Timeline</span>
              </TabsTrigger>
              <TabsTrigger value="flagged" className="flex items-center gap-2 data-[state=active]:bg-gray-700 data-[state=active]:text-orange-500">
                <AlertTriangle className="h-4 w-4" />
                <span className="hidden sm:inline">Flagged</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6">
              {/* Key Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium text-gray-300">Total Pageviews</CardTitle>
                    <Eye className="h-4 w-4 text-orange-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-orange-500">
                      {formatNumber(analytics.totals.pageviews)}
                    </div>
                    <p className="text-xs text-gray-400">
                      All-time page views
                    </p>
                  </CardContent>
                </Card>

                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium text-gray-300">Unique Visitors</CardTitle>
                    <Users className="h-4 w-4 text-orange-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-orange-500">
                      {formatNumber(analytics.totals.uniques)}
                    </div>
                    <p className="text-xs text-gray-400">
                      Individual users tracked
                    </p>
                  </CardContent>
                </Card>

                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium text-gray-300">Chat Questions</CardTitle>
                    <MessageSquare className="h-4 w-4 text-orange-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-orange-500">
                      {formatNumber(analytics.totals.chat_questions)}
                    </div>
                    <p className="text-xs text-gray-400">
                      AI questions processed
                    </p>
                  </CardContent>
                </Card>

                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium text-gray-300">Engagement Rate</CardTitle>
                    <TrendingUp className="h-4 w-4 text-orange-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-orange-500">
                      {analytics.service_info.engagement_rate.toFixed(1)}%
                    </div>
                    <p className="text-xs text-gray-400">
                      Questions per visit
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Service Information */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader>
                    <CardTitle className="text-gray-200">Service Performance</CardTitle>
                    <CardDescription className="text-gray-400">Key performance indicators</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">Questions per User:</span>
                      <Badge className="bg-gray-700 text-orange-500 border-gray-600">
                        {analytics.service_info.questions_per_user.toFixed(2)}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">Total Locations Tracked:</span>
                      <Badge className="bg-gray-700 text-orange-500 border-gray-600">
                        {formatNumber(analytics.visitor_locations.total_tracked)}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">Service Started:</span>
                      <span className="text-sm text-gray-400">
                        {formatDate(analytics.service_info.first_visit)}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">Last Updated:</span>
                      <span className="text-sm text-gray-400">
                        {formatDate(analytics.service_info.last_updated)}
                      </span>
                    </div>
                  </CardContent>
                </Card>

                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader>
                    <CardTitle className="text-gray-200">Geographic Distribution</CardTitle>
                    <CardDescription className="text-gray-400">Visitor location breakdown</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">US States:</span>
                      <Badge className="bg-orange-600 text-white">
                        {Object.keys(analytics.visitor_locations.us_states).length} states
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">International:</span>
                      <Badge className="bg-gray-700 text-gray-300 border-gray-600">
                        {formatNumber(analytics.visitor_locations.international)} visitors
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">Local/Development:</span>
                      <Badge className="bg-gray-700 text-gray-300 border-gray-600">
                        {formatNumber(analytics.visitor_locations.local)} visits
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-300">Unknown Location:</span>
                      <Badge className="bg-gray-700 text-gray-300 border-gray-600">
                        {formatNumber(analytics.visitor_locations.unknown)} visits
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="locations" className="space-y-6">
              <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2 text-gray-200">
                    <Globe className="h-5 w-5 text-orange-500" />
                    <span>Visitor Locations Heat Map</span>
                  </CardTitle>
                  <CardDescription className="text-gray-400">
                    Geographic distribution of website visitors across the United States
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Suspense fallback={
                    <div className="flex items-center justify-center h-64">
                      <div className="text-gray-500">Loading map...</div>
                    </div>
                  }>
                    <USHeatMap />
                  </Suspense>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="traffic" className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Top Pages */}
                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2 text-gray-200">
                      <BarChart3 className="h-5 w-5 text-orange-500" />
                      <span>Top Pages</span>
                    </CardTitle>
                    <CardDescription className="text-gray-400">Most visited pages (last {days} days)</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow className="border-gray-700">
                          <TableHead className="text-gray-400">Page</TableHead>
                          <TableHead className="text-right text-gray-400">Views</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {analytics.top_pages.length === 0 ? (
                          <TableRow className="border-gray-700">
                            <TableCell colSpan={2} className="text-center text-gray-500">
                              No page data available
                            </TableCell>
                          </TableRow>
                        ) : (
                          analytics.top_pages.map((page, index) => (
                            <TableRow key={index} className="border-gray-700">
                              <TableCell className="font-medium text-gray-300">
                                {page.path || '(homepage)'}
                              </TableCell>
                              <TableCell className="text-right text-orange-500">
                                {formatNumber(page.pageviews)}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                {/* Top Referrers */}
                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2 text-gray-200">
                      <Link className="h-5 w-5 text-orange-500" />
                      <span>Top Referrers</span>
                    </CardTitle>
                    <CardDescription className="text-gray-400">Traffic sources (last {days} days)</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow className="border-gray-700">
                          <TableHead className="text-gray-400">Referrer</TableHead>
                          <TableHead className="text-right text-gray-400">Visits</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {analytics.top_referrers.length === 0 ? (
                          <TableRow className="border-gray-700">
                            <TableCell colSpan={2} className="text-center text-gray-500">
                              No referrer data available
                            </TableCell>
                          </TableRow>
                        ) : (
                          analytics.top_referrers.map((referrer, index) => (
                            <TableRow key={index} className="border-gray-700">
                              <TableCell className="font-medium text-gray-300">
                                {referrer.referrer === '(direct)' ? 'Direct Traffic' : referrer.referrer}
                              </TableCell>
                              <TableCell className="text-right text-orange-500">
                                {formatNumber(referrer.visits)}
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="tokens" className="space-y-6">
              {analytics.token_usage?.available ? (
                <>
                  {/* Token Usage Overview */}
                  {analytics.token_usage?.summary && (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                      <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium text-gray-300">Total Tokens</CardTitle>
                          <Zap className="h-4 w-4 text-orange-500" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-orange-500">
                            {formatNumber(analytics.token_usage.summary.total_tokens || 0)}
                          </div>
                          <p className="text-xs text-gray-400">
                            Over {analytics.token_usage.summary.queries_with_tokens || 0} queries
                          </p>
                        </CardContent>
                      </Card>

                      <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium text-gray-300">Avg per Query</CardTitle>
                          <Cpu className="h-4 w-4 text-orange-500" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-orange-500">
                            {Math.round(analytics.token_usage.summary.avg_tokens_per_query || 0)}
                          </div>
                          <p className="text-xs text-gray-400">
                            Tokens per question
                          </p>
                        </CardContent>
                      </Card>

                      <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium text-gray-300">Prompt Tokens</CardTitle>
                          <MessageSquare className="h-4 w-4 text-orange-500" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-orange-500">
                            {formatNumber(analytics.token_usage.summary.total_prompt_tokens || 0)}
                          </div>
                          <p className="text-xs text-gray-400">
                            Input processing
                          </p>
                        </CardContent>
                      </Card>

                      <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium text-gray-300">Completion Tokens</CardTitle>
                          <Eye className="h-4 w-4 text-orange-500" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-orange-500">
                            {formatNumber(analytics.token_usage.summary.total_completion_tokens || 0)}
                          </div>
                          <p className="text-xs text-gray-400">
                            Response generation
                          </p>
                        </CardContent>
                      </Card>
                    </div>
                  )}

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Model Breakdown */}
                    {analytics.token_usage?.model_breakdown && analytics.token_usage.model_breakdown.length > 0 && (
                      <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader>
                          <CardTitle className="flex items-center space-x-2 text-gray-200">
                            <Cpu className="h-5 w-5 text-orange-500" />
                            <span>Model Usage</span>
                          </CardTitle>
                          <CardDescription className="text-gray-400">Token consumption by AI model</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow className="border-gray-700">
                                <TableHead className="text-gray-400">Model</TableHead>
                                <TableHead className="text-gray-400">Provider</TableHead>
                                <TableHead className="text-right text-gray-400">Uses</TableHead>
                                <TableHead className="text-right text-gray-400">Total Tokens</TableHead>
                                <TableHead className="text-right text-gray-400">Avg</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {analytics.token_usage.model_breakdown.map((model: any, index: number) => (
                                <TableRow key={index} className="border-gray-700">
                                  <TableCell className="font-medium text-gray-300">
                                    {model.model_used || 'Unknown'}
                                  </TableCell>
                                  <TableCell>
                                    <Badge className="bg-gray-700 text-gray-300 border-gray-600">
                                      {model.api_provider || 'Unknown'}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="text-right text-gray-300">
                                    {formatNumber(model.usage_count)}
                                  </TableCell>
                                  <TableCell className="text-right text-orange-500">
                                    {formatNumber(model.total_tokens || 0)}
                                  </TableCell>
                                  <TableCell className="text-right text-gray-300">
                                    {Math.round(model.avg_tokens || 0)}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>
                    )}

                    {/* Daily Token Usage */}
                    {analytics.token_usage?.daily_usage && analytics.token_usage.daily_usage.length > 0 && (
                      <Card className="bg-gray-800/50 border-gray-700">
                        <CardHeader>
                          <CardTitle className="flex items-center space-x-2 text-gray-200">
                            <Calendar className="h-5 w-5 text-orange-500" />
                            <span>Daily Token Usage</span>
                          </CardTitle>
                          <CardDescription className="text-gray-400">Token consumption over time (last {days} days)</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow className="border-gray-700">
                                <TableHead className="text-gray-400">Date</TableHead>
                                <TableHead className="text-right text-gray-400">Queries</TableHead>
                                <TableHead className="text-right text-gray-400">Total Tokens</TableHead>
                                <TableHead className="text-right text-gray-400">Avg</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {analytics.token_usage.daily_usage.slice(0, 10).map((day: any, index: number) => (
                                <TableRow key={index} className="border-gray-700">
                                  <TableCell className="font-medium text-gray-300">
                                    {new Date(day.day).toLocaleDateString('en-US', {
                                      month: 'short',
                                      day: 'numeric'
                                    })}
                                  </TableCell>
                                  <TableCell className="text-right text-gray-300">
                                    {formatNumber(day.queries)}
                                  </TableCell>
                                  <TableCell className="text-right text-orange-500">
                                    {formatNumber(day.daily_tokens)}
                                  </TableCell>
                                  <TableCell className="text-right text-gray-300">
                                    {Math.round(day.avg_tokens || 0)}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>
                    )}
                  </div>

                  {/* Token Usage Summary */}
                  {analytics.token_usage?.summary && (
                    <Card className="bg-gray-800/50 border-gray-700">
                      <CardHeader>
                        <CardTitle className="text-gray-200">Token Usage Insights</CardTitle>
                        <CardDescription className="text-gray-400">AI resource consumption analysis</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="text-center p-4 bg-gray-700/50 rounded-lg">
                            <div className="text-2xl font-bold text-orange-500">
                              {analytics.token_usage.summary.unique_models || 0}
                            </div>
                            <p className="text-sm text-gray-400">AI Models Used</p>
                          </div>
                          <div className="text-center p-4 bg-gray-700/50 rounded-lg">
                            <div className="text-2xl font-bold text-orange-500">
                              {analytics.token_usage.summary.unique_providers || 0}
                            </div>
                            <p className="text-sm text-gray-400">API Providers</p>
                          </div>
                          <div className="text-center p-4 bg-gray-700/50 rounded-lg">
                            <div className="text-2xl font-bold text-orange-500">
                              {((analytics.token_usage.summary.total_completion_tokens || 0) / Math.max(analytics.token_usage.summary.total_tokens || 1, 1) * 100).toFixed(1)}%
                            </div>
                            <p className="text-sm text-gray-400">Response Ratio</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              ) : (
                <Card className="bg-gray-800/50 border-gray-700">
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2 text-gray-200">
                      <Zap className="h-5 w-5 text-orange-500" />
                      <span>Token Usage Tracking</span>
                    </CardTitle>
                    <CardDescription className="text-gray-400">AI token consumption analytics</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-center py-8">
                      <Zap className="h-12 w-12 mx-auto text-gray-500 mb-4" />
                      <p className="text-lg font-medium text-gray-300 mb-2">
                        Token Tracking Not Available
                      </p>
                      <p className="text-sm text-gray-400">
                        {analytics.token_usage?.message || analytics.token_usage?.error || 'Token usage tracking is being set up. Check back shortly.'}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="performance" className="space-y-6">
              {analytics.performance ? (
                analytics.performance.available ? (
                  <>
                    {analytics.performance.summary && (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                        <Card className="bg-gray-800/50 border-gray-700">
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-300">Avg Response Time</CardTitle>
                            <TrendingUp className="h-4 w-4 text-orange-500" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-orange-500">
                              {Math.round(analytics.performance.summary.avg_ms || 0)} ms
                            </div>
                            <p className="text-xs text-gray-400">Average over last {days} days</p>
                          </CardContent>
                        </Card>

                        <Card className="bg-gray-800/50 border-gray-700">
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-300">p95 Response Time</CardTitle>
                            <TrendingUp className="h-4 w-4 text-orange-500" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-orange-500">
                              {Math.round(analytics.performance.summary.p95_ms || 0)} ms
                            </div>
                            <p className="text-xs text-gray-400">95th percentile</p>
                          </CardContent>
                        </Card>

                        <Card className="bg-gray-800/50 border-gray-700">
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-300">Success Rate</CardTitle>
                            <TrendingUp className="h-4 w-4 text-orange-500" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-orange-500">
                              {((analytics.performance.summary.success_rate || 0) * 100).toFixed(1)}%
                            </div>
                            <p className="text-xs text-gray-400">Successful responses</p>
                          </CardContent>
                        </Card>

                        <Card className="bg-gray-800/50 border-gray-700">
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-300">Avg Answer Size</CardTitle>
                            <BarChart3 className="h-4 w-4 text-orange-500" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-orange-500">
                              {Math.round(analytics.performance.summary.avg_answer_chars || 0)} chars
                            </div>
                            <p className="text-xs text-gray-400">Response length</p>
                          </CardContent>
                        </Card>
                      </div>
                    )}

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      {analytics.performance.by_provider && analytics.performance.by_provider.length > 0 && (
                        <Card className="bg-gray-800/50 border-gray-700">
                          <CardHeader>
                            <CardTitle className="text-gray-200">Performance by Provider</CardTitle>
                            <CardDescription className="text-gray-400">Comparative performance metrics</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <Table>
                              <TableHeader>
                                <TableRow className="border-gray-700">
                                  <TableHead className="text-gray-400">Provider</TableHead>
                                  <TableHead className="text-right text-gray-400">Avg ms</TableHead>
                                  <TableHead className="text-right text-gray-400">p95 ms</TableHead>
                                  <TableHead className="text-right text-gray-400">Success</TableHead>
                                  <TableHead className="text-right text-gray-400">Queries</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {analytics.performance.by_provider.map((row: any, idx: number) => (
                                  <TableRow key={idx} className="border-gray-700">
                                    <TableCell className="font-medium text-gray-300">{row.provider}</TableCell>
                                    <TableCell className="text-right text-orange-500">{Math.round(row.avg_ms || 0)}</TableCell>
                                    <TableCell className="text-right text-orange-500">{Math.round(row.p95_ms || 0)}</TableCell>
                                    <TableCell className="text-right text-gray-300">{((row.success_rate || 0) * 100).toFixed(1)}%</TableCell>
                                    <TableCell className="text-right text-gray-300">{row.queries}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </CardContent>
                        </Card>
                      )}

                      {analytics.performance.daily && analytics.performance.daily.length > 0 && (
                        <Card className="bg-gray-800/50 border-gray-700">
                          <CardHeader>
                            <CardTitle className="text-gray-200">Daily Performance</CardTitle>
                            <CardDescription className="text-gray-400">Average and p95 response times</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <Table>
                              <TableHeader>
                                <TableRow className="border-gray-700">
                                  <TableHead className="text-gray-400">Date</TableHead>
                                  <TableHead className="text-right text-gray-400">Avg ms</TableHead>
                                  <TableHead className="text-right text-gray-400">p95 ms</TableHead>
                                  <TableHead className="text-right text-gray-400">Queries</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {analytics.performance.daily.slice(0, 10).map((d: any, idx: number) => (
                                  <TableRow key={idx} className="border-gray-700">
                                    <TableCell className="font-medium text-gray-300">{new Date(d.day).toLocaleDateString('en-US', {month:'short', day:'numeric'})}</TableCell>
                                    <TableCell className="text-right text-orange-500">{Math.round(d.avg_ms || 0)}</TableCell>
                                    <TableCell className="text-right text-orange-500">{Math.round(d.p95_ms || 0)}</TableCell>
                                    <TableCell className="text-right text-gray-300">{d.queries}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </CardContent>
                        </Card>
                      )}
                    </div>
                  </>
                ) : (
                  <Card className="bg-gray-800/50 border-gray-700">
                    <CardHeader>
                      <CardTitle className="text-gray-200">Performance Analytics</CardTitle>
                      <CardDescription className="text-gray-400">{analytics.performance.message || analytics.performance.error || 'Performance data not yet available.'}</CardDescription>
                    </CardHeader>
                  </Card>
                )
              ) : null}
            </TabsContent>

            <CacheMetricsTab adminToken={adminToken} />

            <TabsContent value="timeline" className="space-y-6">
              <Card className="bg-gray-800/50 border-gray-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2 text-gray-200">
                    <Calendar className="h-5 w-5 text-orange-500" />
                    <span>Daily Activity Timeline</span>
                  </CardTitle>
                  <CardDescription className="text-gray-400">
                    Daily breakdown of pageviews, unique visitors, and chat questions (last {days} days)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-gray-700">
                        <TableHead className="text-gray-400">Date</TableHead>
                        <TableHead className="text-right text-gray-400">Pageviews</TableHead>
                        <TableHead className="text-right text-gray-400">Unique Visitors</TableHead>
                        <TableHead className="text-right text-gray-400">Chat Questions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {analytics.by_day.length === 0 ? (
                        <TableRow className="border-gray-700">
                          <TableCell colSpan={4} className="text-center text-gray-500">
                            No daily data available for the selected period
                          </TableCell>
                        </TableRow>
                      ) : (
                        analytics.by_day.map((day, index) => (
                          <TableRow key={index} className="border-gray-700">
                            <TableCell className="font-medium text-gray-300">
                              {new Date(day.day).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric'
                              })}
                            </TableCell>
                            <TableCell className="text-right text-orange-500">
                              {formatNumber(day.pageviews)}
                            </TableCell>
                            <TableCell className="text-right text-orange-500">
                              {formatNumber(day.uniques)}
                            </TableCell>
                            <TableCell className="text-right text-orange-500">
                              {formatNumber(day.chat_questions)}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <TimelineView />
            </TabsContent>

            {/* Flagged Responses Tab - Hallucination Detection */}
            <TabsContent value="flagged" className="space-y-6">
              <Card className="bg-slate-800/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2 text-orange-500">
                    <AlertTriangle className="h-5 w-5" />
                    <span>Flagged Responses</span>
                  </CardTitle>
                  <CardDescription>
                    Responses flagged for potential hallucinations, weak retrieval, or suspicious citations.
                    Review these entries to improve corpus quality and RAG accuracy.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {/* Alert Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <Card className="bg-red-900/20 border-red-700">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium text-red-400">Weak Retrievals</CardTitle>
                          <AlertTriangle className="h-4 w-4 text-red-500" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-red-500">--</div>
                          <p className="text-xs text-red-400/70">Best chunk score &lt; 0.55</p>
                        </CardContent>
                      </Card>

                      <Card className="bg-yellow-900/20 border-yellow-700">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium text-yellow-400">Suspicious Citations</CardTitle>
                          <AlertCircle className="h-4 w-4 text-yellow-500" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-yellow-500">--</div>
                          <p className="text-xs text-yellow-400/70">Citation verification failed</p>
                        </CardContent>
                      </Card>

                      <Card className="bg-orange-900/20 border-orange-700">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium text-orange-400">Invalid URLs</CardTitle>
                          <Link className="h-4 w-4 text-orange-500" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-orange-500">--</div>
                          <p className="text-xs text-orange-400/70">URLs not in whitelist</p>
                        </CardContent>
                      </Card>
                    </div>

                    {/* Info Box */}
                    <Card className="bg-slate-700/30 border-slate-600">
                      <CardContent className="pt-6">
                        <div className="flex items-start gap-4">
                          <Shield className="h-8 w-8 text-orange-500 flex-shrink-0" />
                          <div>
                            <h4 className="font-semibold text-orange-500 mb-2">Hallucination Prevention System</h4>
                            <p className="text-sm text-gray-300 mb-3">
                              The RAG pipeline now includes multiple layers of hallucination detection:
                            </p>
                            <ul className="text-sm text-gray-400 space-y-2">
                              <li className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4 text-green-500" />
                                <span><strong>Relevance Threshold:</strong> Chunks below 0.45 similarity are rejected</span>
                              </li>
                              <li className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4 text-green-500" />
                                <span><strong>URL Validation:</strong> All source URLs verified against whitelist</span>
                              </li>
                              <li className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4 text-green-500" />
                                <span><strong>Citation Verification:</strong> Claims cross-checked with source chunks</span>
                              </li>
                              <li className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4 text-green-500" />
                                <span><strong>Explicit Boundaries:</strong> Context chunks clearly delimited for LLM</span>
                              </li>
                            </ul>
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    {/* Placeholder for flagged entries table */}
                    <Card className="bg-slate-700/30 border-slate-600">
                      <CardHeader>
                        <CardTitle className="text-sm text-gray-300">Recent Flagged Entries</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-center py-8 text-gray-400">
                          <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-gray-500" />
                          <p>Flagged response logging is now active.</p>
                          <p className="text-sm mt-2">Responses with weak retrieval or citation issues will appear here.</p>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        )}

        {/* Footer */}
        <div className="text-center mt-12 text-gray-500">
          <p>Veterans Benefits AI - Admin Analytics Dashboard</p>
          <p className="text-sm mt-1">
            Data refreshes automatically every minute • Last updated: {analytics?.service_info.last_updated ? formatDate(analytics.service_info.last_updated) : 'Unknown'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default AdminAnalytics;
