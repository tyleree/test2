import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, RefreshCw, Users, MessageSquare, Eye, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { useToast } from "@/hooks/use-toast";

interface StatsData {
  ask_count: number;
  visit_count: number;
  unique_visitors: number;
  first_visit: string;
  last_updated: string;
}

const Stats = () => {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const fetchStats = async () => {
    try {
      const response = await fetch('/metrics');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setStats(data);
      setError(null);
    } catch (err) {
      console.error('Error fetching stats:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch statistics');
      toast({
        title: "Error",
        description: "Failed to fetch statistics. Please try again.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchStats, 30000);
    
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setLoading(true);
    fetchStats();
  };

  const formatDate = (isoString: string) => {
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

  const calculateEngagementRate = () => {
    if (!stats || stats.visit_count === 0) return 0;
    return (stats.ask_count / stats.visit_count * 100);
  };

  const calculateQuestionsPerUser = () => {
    if (!stats || stats.unique_visitors === 0) return 0;
    return stats.ask_count / stats.unique_visitors;
  };

  if (loading && !stats) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background">
        <div className="flex items-center space-x-2">
          <RefreshCw className="h-6 w-6 animate-spin" />
          <span className="text-lg">Loading statistics...</span>
        </div>
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold text-destructive">Error Loading Statistics</h1>
          <p className="text-muted-foreground">{error}</p>
          <Button onClick={handleRefresh} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Try Again
          </Button>
          <div className="mt-4">
            <Button asChild variant="ghost">
              <Link to="/">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to Home
              </Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background py-12 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="flex items-center justify-center mb-6">
            <Button asChild variant="ghost" className="mr-4">
              <Link to="/">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to Home
              </Link>
            </Button>
            <Button onClick={handleRefresh} variant="outline" disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
          
          <h1 className="text-5xl md:text-6xl font-bold mb-4 text-transparent bg-clip-text bg-gradient-to-r from-accent to-primary">
            Statistics
          </h1>
          <p className="text-xl text-muted-foreground mb-4">
            Veterans Benefits AI Usage Analytics
          </p>
          {stats && (
            <Badge variant="secondary" className="text-sm">
              Last updated: {formatDate(stats.last_updated)}
            </Badge>
          )}
        </div>

        {stats && (
          <>
            {/* Main Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
              {/* Questions Asked */}
              <Card className="text-center">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-center space-x-2">
                    <MessageSquare className="h-5 w-5 text-blue-500" />
                    <span>Questions Asked</span>
                  </CardTitle>
                  <CardDescription>Total questions processed by our AI</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-bold text-blue-500 mb-2">
                    {stats.ask_count.toLocaleString()}
                  </div>
                </CardContent>
              </Card>

              {/* Website Visits */}
              <Card className="text-center">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-center space-x-2">
                    <Eye className="h-5 w-5 text-green-500" />
                    <span>Website Visits</span>
                  </CardTitle>
                  <CardDescription>Total page views since launch</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-bold text-green-500 mb-2">
                    {stats.visit_count.toLocaleString()}
                  </div>
                </CardContent>
              </Card>

              {/* Unique Visitors */}
              <Card className="text-center">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-center space-x-2">
                    <Users className="h-5 w-5 text-purple-500" />
                    <span>Unique Visitors</span>
                  </CardTitle>
                  <CardDescription>Different users who visited our site</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-bold text-purple-500 mb-2">
                    {stats.unique_visitors.toLocaleString()}
                  </div>
                </CardContent>
              </Card>

              {/* Engagement Rate */}
              <Card className="text-center">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-center space-x-2">
                    <TrendingUp className="h-5 w-5 text-orange-500" />
                    <span>Engagement Rate</span>
                  </CardTitle>
                  <CardDescription>Percentage of visits that asked questions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-bold text-orange-500 mb-2">
                    {calculateEngagementRate().toFixed(1)}%
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Detailed Analytics */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Service Information */}
              <Card>
                <CardHeader>
                  <CardTitle>Service Information</CardTitle>
                  <CardDescription>Details about our service performance</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="font-medium">Service Started:</span>
                    <span className="text-muted-foreground">{formatDate(stats.first_visit)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="font-medium">Questions per Visit:</span>
                    <span className="text-muted-foreground">
                      {(stats.ask_count / Math.max(stats.visit_count, 1)).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="font-medium">Questions per Unique User:</span>
                    <span className="text-muted-foreground">
                      {calculateQuestionsPerUser().toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="font-medium">Return Visitor Rate:</span>
                    <span className="text-muted-foreground">
                      {stats.unique_visitors > 0 
                        ? ((1 - stats.unique_visitors / stats.visit_count) * 100).toFixed(1)
                        : 0}%
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* Real-time Updates */}
              <Card>
                <CardHeader>
                  <CardTitle>Real-time Updates</CardTitle>
                  <CardDescription>Live statistics and system status</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Status:</span>
                    <Badge variant="default" className="bg-green-500">
                      Live
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Auto-refresh:</span>
                    <Badge variant="secondary">
                      Every 30 seconds
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Data Persistence:</span>
                    <Badge variant="outline">
                      Across Restarts
                    </Badge>
                  </div>
                  <div className="text-sm text-muted-foreground pt-2">
                    Statistics are updated in real-time and persist across server restarts.
                    All data is stored securely and anonymously.
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Footer */}
            <div className="text-center mt-12 text-muted-foreground">
              <p>Veterans Benefits AI - Trusted data, free forever</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default Stats;
