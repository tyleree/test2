import { useEffect, useState, Suspense, lazy } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ArrowLeft, RefreshCw, Users, MessageSquare, Eye, TrendingUp, Globe, BarChart3, Calendar, Link, Cpu, Zap, Clock, Hash, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { useToast } from "@/hooks/use-toast";

// Lazy load heavy map component
const USHeatMap = lazy(() => import("@/components/USHeatMap"));

interface TimelineEntry {
  id: number;
  timestamp: string;
  question: string;
  question_hash: string;
  cache_mode: string;
  semantic_similarity?: number;
  answer_preview: string;
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
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Questions</CardTitle>
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{timelineData.stats.total_questions}</div>
              <p className="text-xs text-muted-foreground">Last 24 hours</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Cache Hit Rate</CardTitle>
              <Zap className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                {timelineData.stats.cache_hit_rate?.toFixed(1) || 0}%
              </div>
              <p className="text-xs text-muted-foreground">
                {(timelineData.stats.exact_hits || 0) + (timelineData.stats.semantic_hits || 0)} hits
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Avg Latency</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-blue-600">
                {Math.round(timelineData.stats.avg_latency || 0)}ms
              </div>
              <p className="text-xs text-muted-foreground">Response time</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Tokens Used</CardTitle>
              <Hash className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-purple-600">
                {formatTokens(timelineData.stats.total_tokens_used)}
              </div>
              <p className="text-xs text-muted-foreground">Total consumption</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Question Timeline</CardTitle>
          <CardDescription>
            Comprehensive view of all questions, cache performance, and token usage
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 mb-4">
            <Button
              variant={filter === 'all' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter('all')}
            >
              All Questions
            </Button>
            <Button
              variant={filter === 'exact_hit' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter('exact_hit')}
            >
              Exact Hits
            </Button>
            <Button
              variant={filter === 'semantic_hit' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter('semantic_hit')}
            >
              Semantic Hits
            </Button>
            <Button
              variant={filter === 'miss' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter('miss')}
            >
              Cache Misses
            </Button>
          </div>

          {/* Timeline Table */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Question</TableHead>
                  <TableHead>Cache Mode</TableHead>
                  <TableHead>Similarity</TableHead>
                  <TableHead>Latency</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>Citations</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {timelineData?.entries?.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-sm">
                      {formatTimestamp(entry.timestamp)}
                    </TableCell>
                    <TableCell className="max-w-md">
                      <div className="truncate" title={entry.question}>
                        {entry.question}
                      </div>
                      {entry.answer_preview && (
                        <div className="text-xs text-muted-foreground mt-1 truncate">
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
                        <Badge variant="outline">
                          {(entry.semantic_similarity * 100).toFixed(1)}%
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {entry.latency_ms}ms
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        <div className="font-medium">
                          {formatTokens(entry.token_usage?.total_tokens || 0)}
                        </div>
                        {entry.token_usage?.tokens_big && (
                          <div className="text-xs text-muted-foreground">
                            Big: {formatTokens(entry.token_usage.tokens_big)}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {entry.citations_count}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedQuestion(entry)}
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
            <div className="text-center py-8 text-muted-foreground">
              No questions found for the selected filter.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Question Details Modal/Dialog would go here */}
      {selectedQuestion && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Question Details</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedQuestion(null)}
              className="absolute top-4 right-4"
            >
              ✕
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="font-medium">Question:</label>
              <p className="mt-1">{selectedQuestion.question}</p>
            </div>
            <div>
              <label className="font-medium">Answer Preview:</label>
              <p className="mt-1 text-sm text-muted-foreground">{selectedQuestion.answer_preview}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="font-medium">Cache Mode:</label>
                <div className="mt-1">{getCacheModeBadge(selectedQuestion.cache_mode)}</div>
              </div>
              <div>
                <label className="font-medium">Latency:</label>
                <p className="mt-1">{selectedQuestion.latency_ms}ms</p>
              </div>
            </div>
            <div>
              <label className="font-medium">Token Usage:</label>
              <div className="mt-1 text-sm space-y-1">
                <div>Total: {formatTokens(selectedQuestion.token_usage?.total_tokens || 0)}</div>
                {selectedQuestion.token_usage?.tokens_big && (
                  <div>Big Model: {formatTokens(selectedQuestion.token_usage.tokens_big)}</div>
                )}
                {selectedQuestion.token_usage?.tokens_small && (
                  <div>Small Model: {formatTokens(selectedQuestion.token_usage.tokens_small)}</div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
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
      <div className="min-h-screen flex flex-col items-center justify-center bg-background">
        <div className="text-center space-y-4 max-w-md">
          <h1 className="text-3xl font-bold text-destructive">🔒 Admin Access Required</h1>
          <p className="text-muted-foreground">
            This page requires a valid admin token. Please contact the administrator for access.
          </p>
          <p className="text-sm text-muted-foreground">
            Access URL format: <code>/admin/analytics?token=YOUR_TOKEN</code>
          </p>
          <div className="mt-6">
            <Button asChild variant="outline">
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
    <div className="min-h-screen bg-background py-8 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center space-x-4">
            <Button asChild variant="ghost">
              <RouterLink to="/">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Home
              </RouterLink>
            </Button>
            <div>
              <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-accent to-primary">
                📊 Admin Analytics
              </h1>
              <p className="text-muted-foreground">Comprehensive site analytics and insights</p>
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="px-3 py-2 border rounded-md bg-background"
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last year</option>
            </select>
            <Button onClick={handleRefresh} variant="outline" disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Badge variant="secondary">
              Admin Access
            </Badge>
          </div>
        </div>

        {analytics && (
          <Tabs defaultValue="overview" className="space-y-6">
            <TabsList className="grid w-full grid-cols-6">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="locations">Locations</TabsTrigger>
              <TabsTrigger value="traffic">Traffic</TabsTrigger>
              <TabsTrigger value="tokens">Tokens</TabsTrigger>
              <TabsTrigger value="performance">Performance</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6">
              {/* Key Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Total Pageviews</CardTitle>
                    <Eye className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-green-600">
                      {formatNumber(analytics.totals.pageviews)}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      All-time page views
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Unique Visitors</CardTitle>
                    <Users className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-purple-600">
                      {formatNumber(analytics.totals.uniques)}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Individual users tracked
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Chat Questions</CardTitle>
                    <MessageSquare className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-blue-600">
                      {formatNumber(analytics.totals.chat_questions)}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      AI questions processed
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Engagement Rate</CardTitle>
                    <TrendingUp className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-orange-600">
                      {analytics.service_info.engagement_rate.toFixed(1)}%
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Questions per visit
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Service Information */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Service Performance</CardTitle>
                    <CardDescription>Key performance indicators</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="font-medium">Questions per User:</span>
                      <Badge variant="outline">
                        {analytics.service_info.questions_per_user.toFixed(2)}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium">Total Locations Tracked:</span>
                      <Badge variant="outline">
                        {formatNumber(analytics.visitor_locations.total_tracked)}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium">Service Started:</span>
                      <span className="text-sm text-muted-foreground">
                        {formatDate(analytics.service_info.first_visit)}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium">Last Updated:</span>
                      <span className="text-sm text-muted-foreground">
                        {formatDate(analytics.service_info.last_updated)}
                      </span>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Geographic Distribution</CardTitle>
                    <CardDescription>Visitor location breakdown</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="font-medium">US States:</span>
                      <Badge variant="default">
                        {Object.keys(analytics.visitor_locations.us_states).length} states
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium">International:</span>
                      <Badge variant="secondary">
                        {formatNumber(analytics.visitor_locations.international)} visitors
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium">Local/Development:</span>
                      <Badge variant="outline">
                        {formatNumber(analytics.visitor_locations.local)} visits
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="font-medium">Unknown Location:</span>
                      <Badge variant="outline">
                        {formatNumber(analytics.visitor_locations.unknown)} visits
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="locations" className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Globe className="h-5 w-5" />
                    <span>Visitor Locations Heat Map</span>
                  </CardTitle>
                  <CardDescription>
                    Geographic distribution of website visitors across the United States
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Suspense fallback={
                    <div className="flex items-center justify-center h-64">
                      <div className="text-muted-foreground">Loading map...</div>
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
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2">
                      <BarChart3 className="h-5 w-5" />
                      <span>Top Pages</span>
                    </CardTitle>
                    <CardDescription>Most visited pages (last {days} days)</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Page</TableHead>
                          <TableHead className="text-right">Views</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {analytics.top_pages.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={2} className="text-center text-muted-foreground">
                              No page data available
                            </TableCell>
                          </TableRow>
                        ) : (
                          analytics.top_pages.map((page, index) => (
                            <TableRow key={index}>
                              <TableCell className="font-medium">
                                {page.path || '(homepage)'}
                              </TableCell>
                              <TableCell className="text-right">
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
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2">
                      <Link className="h-5 w-5" />
                      <span>Top Referrers</span>
                    </CardTitle>
                    <CardDescription>Traffic sources (last {days} days)</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Referrer</TableHead>
                          <TableHead className="text-right">Visits</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {analytics.top_referrers.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={2} className="text-center text-muted-foreground">
                              No referrer data available
                            </TableCell>
                          </TableRow>
                        ) : (
                          analytics.top_referrers.map((referrer, index) => (
                            <TableRow key={index}>
                              <TableCell className="font-medium">
                                {referrer.referrer === '(direct)' ? 'Direct Traffic' : referrer.referrer}
                              </TableCell>
                              <TableCell className="text-right">
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
              {analytics.token_usage.available ? (
                <>
                  {/* Token Usage Overview */}
                  {analytics.token_usage.summary && (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                      <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium">Total Tokens</CardTitle>
                          <Zap className="h-4 w-4 text-muted-foreground" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-yellow-600">
                            {formatNumber(analytics.token_usage.summary.total_tokens)}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Over {analytics.token_usage.summary.queries_with_tokens} queries
                          </p>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium">Avg per Query</CardTitle>
                          <Cpu className="h-4 w-4 text-muted-foreground" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-blue-600">
                            {Math.round(analytics.token_usage.summary.avg_tokens_per_query || 0)}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Tokens per question
                          </p>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium">Prompt Tokens</CardTitle>
                          <MessageSquare className="h-4 w-4 text-muted-foreground" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-green-600">
                            {formatNumber(analytics.token_usage.summary.total_prompt_tokens)}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Input processing
                          </p>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm font-medium">Completion Tokens</CardTitle>
                          <Eye className="h-4 w-4 text-muted-foreground" />
                        </CardHeader>
                        <CardContent>
                          <div className="text-2xl font-bold text-purple-600">
                            {formatNumber(analytics.token_usage.summary.total_completion_tokens)}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Response generation
                          </p>
                        </CardContent>
                      </Card>
                    </div>
                  )}

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Model Breakdown */}
                    {analytics.token_usage.model_breakdown && analytics.token_usage.model_breakdown.length > 0 && (
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center space-x-2">
                            <Cpu className="h-5 w-5" />
                            <span>Model Usage</span>
                          </CardTitle>
                          <CardDescription>Token consumption by AI model</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Model</TableHead>
                                <TableHead>Provider</TableHead>
                                <TableHead className="text-right">Uses</TableHead>
                                <TableHead className="text-right">Total Tokens</TableHead>
                                <TableHead className="text-right">Avg</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {analytics.token_usage.model_breakdown.map((model, index) => (
                                <TableRow key={index}>
                                  <TableCell className="font-medium">
                                    {model.model_used || 'Unknown'}
                                  </TableCell>
                                  <TableCell>
                                    <Badge variant="outline">
                                      {model.api_provider || 'Unknown'}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {formatNumber(model.usage_count)}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {formatNumber(model.total_tokens || 0)}
                                  </TableCell>
                                  <TableCell className="text-right">
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
                    {analytics.token_usage.daily_usage && analytics.token_usage.daily_usage.length > 0 && (
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center space-x-2">
                            <Calendar className="h-5 w-5" />
                            <span>Daily Token Usage</span>
                          </CardTitle>
                          <CardDescription>Token consumption over time (last {days} days)</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Date</TableHead>
                                <TableHead className="text-right">Queries</TableHead>
                                <TableHead className="text-right">Total Tokens</TableHead>
                                <TableHead className="text-right">Avg</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {analytics.token_usage.daily_usage.slice(0, 10).map((day, index) => (
                                <TableRow key={index}>
                                  <TableCell className="font-medium">
                                    {new Date(day.day).toLocaleDateString('en-US', {
                                      month: 'short',
                                      day: 'numeric'
                                    })}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {formatNumber(day.queries)}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {formatNumber(day.daily_tokens)}
                                  </TableCell>
                                  <TableCell className="text-right">
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
                  {analytics.token_usage.summary && (
                    <Card>
                      <CardHeader>
                        <CardTitle>Token Usage Insights</CardTitle>
                        <CardDescription>AI resource consumption analysis</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="text-center p-4 bg-muted rounded-lg">
                            <div className="text-2xl font-bold text-primary">
                              {analytics.token_usage.summary.unique_models}
                            </div>
                            <p className="text-sm text-muted-foreground">AI Models Used</p>
                          </div>
                          <div className="text-center p-4 bg-muted rounded-lg">
                            <div className="text-2xl font-bold text-primary">
                              {analytics.token_usage.summary.unique_providers}
                            </div>
                            <p className="text-sm text-muted-foreground">API Providers</p>
                          </div>
                          <div className="text-center p-4 bg-muted rounded-lg">
                            <div className="text-2xl font-bold text-primary">
                              {((analytics.token_usage.summary.total_completion_tokens / Math.max(analytics.token_usage.summary.total_tokens, 1)) * 100).toFixed(1)}%
                            </div>
                            <p className="text-sm text-muted-foreground">Response Ratio</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              ) : (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2">
                      <Zap className="h-5 w-5" />
                      <span>Token Usage Tracking</span>
                    </CardTitle>
                    <CardDescription>AI token consumption analytics</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-center py-8">
                      <Zap className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                      <p className="text-lg font-medium text-muted-foreground mb-2">
                        Token Tracking Not Available
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {analytics.token_usage.message || analytics.token_usage.error || 'Token usage tracking is being set up. Check back shortly.'}
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
                        <Card>
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Avg Response Time</CardTitle>
                            <TrendingUp className="h-4 w-4 text-muted-foreground" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-blue-600">
                              {Math.round(analytics.performance.summary.avg_ms || 0)} ms
                            </div>
                            <p className="text-xs text-muted-foreground">Average over last {days} days</p>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">p95 Response Time</CardTitle>
                            <TrendingUp className="h-4 w-4 text-muted-foreground" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-orange-600">
                              {Math.round(analytics.performance.summary.p95_ms || 0)} ms
                            </div>
                            <p className="text-xs text-muted-foreground">95th percentile</p>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
                            <TrendingUp className="h-4 w-4 text-muted-foreground" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-green-600">
                              {((analytics.performance.summary.success_rate || 0) * 100).toFixed(1)}%
                            </div>
                            <p className="text-xs text-muted-foreground">Successful responses</p>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Avg Answer Size</CardTitle>
                            <BarChart3 className="h-4 w-4 text-muted-foreground" />
                          </CardHeader>
                          <CardContent>
                            <div className="text-2xl font-bold text-purple-600">
                              {Math.round(analytics.performance.summary.avg_answer_chars || 0)} chars
                            </div>
                            <p className="text-xs text-muted-foreground">Response length</p>
                          </CardContent>
                        </Card>
                      </div>
                    )}

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      {analytics.performance.by_provider && analytics.performance.by_provider.length > 0 && (
                        <Card>
                          <CardHeader>
                            <CardTitle>Performance by Provider</CardTitle>
                            <CardDescription>Comparative performance metrics</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Provider</TableHead>
                                  <TableHead className="text-right">Avg ms</TableHead>
                                  <TableHead className="text-right">p95 ms</TableHead>
                                  <TableHead className="text-right">Success</TableHead>
                                  <TableHead className="text-right">Queries</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {analytics.performance.by_provider.map((row: any, idx: number) => (
                                  <TableRow key={idx}>
                                    <TableCell className="font-medium">{row.provider}</TableCell>
                                    <TableCell className="text-right">{Math.round(row.avg_ms || 0)}</TableCell>
                                    <TableCell className="text-right">{Math.round(row.p95_ms || 0)}</TableCell>
                                    <TableCell className="text-right">{((row.success_rate || 0) * 100).toFixed(1)}%</TableCell>
                                    <TableCell className="text-right">{row.queries}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </CardContent>
                        </Card>
                      )}

                      {analytics.performance.daily && analytics.performance.daily.length > 0 && (
                        <Card>
                          <CardHeader>
                            <CardTitle>Daily Performance</CardTitle>
                            <CardDescription>Average and p95 response times</CardDescription>
                          </CardHeader>
                          <CardContent>
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Date</TableHead>
                                  <TableHead className="text-right">Avg ms</TableHead>
                                  <TableHead className="text-right">p95 ms</TableHead>
                                  <TableHead className="text-right">Queries</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {analytics.performance.daily.slice(0, 10).map((d: any, idx: number) => (
                                  <TableRow key={idx}>
                                    <TableCell className="font-medium">{new Date(d.day).toLocaleDateString('en-US', {month:'short', day:'numeric'})}</TableCell>
                                    <TableCell className="text-right">{Math.round(d.avg_ms || 0)}</TableCell>
                                    <TableCell className="text-right">{Math.round(d.p95_ms || 0)}</TableCell>
                                    <TableCell className="text-right">{d.queries}</TableCell>
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
                  <Card>
                    <CardHeader>
                      <CardTitle>Performance Analytics</CardTitle>
                      <CardDescription>{analytics.performance.message || analytics.performance.error || 'Performance data not yet available.'}</CardDescription>
                    </CardHeader>
                  </Card>
                )
              ) : null}
            </TabsContent>

            <TabsContent value="timeline" className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Calendar className="h-5 w-5" />
                    <span>Daily Activity Timeline</span>
                  </CardTitle>
                  <CardDescription>
                    Daily breakdown of pageviews, unique visitors, and chat questions (last {days} days)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead className="text-right">Pageviews</TableHead>
                        <TableHead className="text-right">Unique Visitors</TableHead>
                        <TableHead className="text-right">Chat Questions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {analytics.by_day.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center text-muted-foreground">
                            No daily data available for the selected period
                          </TableCell>
                        </TableRow>
                      ) : (
                        analytics.by_day.map((day, index) => (
                          <TableRow key={index}>
                            <TableCell className="font-medium">
                              {new Date(day.day).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric'
                              })}
                            </TableCell>
                            <TableCell className="text-right">
                              {formatNumber(day.pageviews)}
                            </TableCell>
                            <TableCell className="text-right">
                              {formatNumber(day.uniques)}
                            </TableCell>
                            <TableCell className="text-right">
                              {formatNumber(day.chat_questions)}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="timeline" className="space-y-6">
              <TimelineView />
            </TabsContent>
          </Tabs>
        )}

        {/* Footer */}
        <div className="text-center mt-12 text-muted-foreground">
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
