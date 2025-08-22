import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ArrowLeft, RefreshCw, Users, MessageSquare, Eye, TrendingUp, Globe, BarChart3, Calendar, Link } from "lucide-react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { useToast } from "@/hooks/use-toast";
import USHeatMap from "@/components/USHeatMap";

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
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="locations">Locations</TabsTrigger>
              <TabsTrigger value="traffic">Traffic</TabsTrigger>
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
                  <USHeatMap />
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
