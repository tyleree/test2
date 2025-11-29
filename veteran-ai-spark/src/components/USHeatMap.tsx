import React, { useState, useEffect } from "react";
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import { scaleLinear } from "d3-scale";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface LocationData {
  us_states: Record<string, number>;
  international: number;
  local: number;
  unknown: number;
  total_tracked: number;
}

interface USHeatMapProps {
  className?: string;
}

// US States topology - served locally for reliability (no CDN dependency)
const geoUrl = "/static/us-states.json";

// FIPS code to state abbreviation mapping (us-atlas uses FIPS codes as IDs)
const fipsToState: Record<string, string> = {
  "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
  "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
  "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
  "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
  "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
  "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
  "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
  "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
  "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
  "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
  "56": "WY", "72": "PR"
};

// State name mapping for tooltips
const stateNames: Record<string, string> = {
  "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
  "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", 
  "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", 
  "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", 
  "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", 
  "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", 
  "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", 
  "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", 
  "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", 
  "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", 
  "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico"
};

export const USHeatMap: React.FC<USHeatMapProps> = ({ className }) => {
  const [locationData, setLocationData] = useState<LocationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredState, setHoveredState] = useState<string | null>(null);

  useEffect(() => {
    const fetchLocationData = async () => {
      try {
        const response = await fetch('/api/locations');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        console.log('🗺️ Heat map received location data:', data);
        console.log('🗺️ US states data:', data.us_states);
        console.log('🗺️ Available state codes:', Object.keys(data.us_states || {}));
        setLocationData(data);
        setError(null);
      } catch (err) {
        console.error('Error fetching location data:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch location data');
      } finally {
        setLoading(false);
      }
    };

    fetchLocationData();
    
    // Refresh location data every 30 seconds
    const interval = setInterval(fetchLocationData, 30000);
    
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Visitor Locations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-64">
            <div className="animate-pulse text-muted-foreground">Loading map...</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error || !locationData) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Visitor Locations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            {error ? `Error: ${error}` : 'No location data available'}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Create color scale based on visitor counts
  const stateValues = Object.values(locationData.us_states);
  const maxCount = stateValues.length > 0 ? Math.max(...stateValues) : 1;
  const minCount = stateValues.length > 0 ? Math.min(...stateValues.filter(v => v > 0)) : 0;
  
  console.log('🎨 Heat map color scale:', { maxCount, minCount, stateValues });
  
  const colorScale = scaleLinear<string>()
    .domain([0, maxCount])
    .range(["#e0e7ff", "#3b82f6"]); // Light blue to blue

  // Get state visitor count
  const getStateCount = (stateCode: string): number => {
    if (!stateCode || !locationData) return 0;
    
    // Try multiple variations of the state code
    const variations = [
      stateCode.toUpperCase(),
      stateCode.toLowerCase(),
      stateCode
    ];
    
    for (const variation of variations) {
      if (locationData.us_states[variation] !== undefined) {
        return locationData.us_states[variation];
      }
    }
    
    return 0;
  };

  // Get state color based on visitor count
  const getStateColor = (stateCode: string): string => {
    const count = getStateCount(stateCode);
    if (count === 0) return "#f8fafc"; // Very light gray for no visitors
    return colorScale(count);
  };

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Visitor Locations</span>
          <Badge variant="secondary" className="text-xs">
            {locationData.total_tracked} tracked
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Heat Map */}
          <div className="relative">
            <ComposableMap
              projection="geoAlbersUsa"
              projectionConfig={{
                scale: 1000,
              }}
              width={800}
              height={500}
              className="w-full h-auto"
            >
              <Geographies geography={geoUrl}>
                {({ geographies }) =>
                  geographies.map((geo) => {
                    // Convert FIPS code (geo.id) to state abbreviation
                    const fipsCode = geo.id as string;
                    const stateCode = fipsToState[fipsCode] || fipsCode;
                    const count = getStateCount(stateCode);
                    const isHovered = hoveredState === stateCode;
                    
                    return (
                      <Geography
                        key={geo.rsmKey}
                        geography={geo}
                        fill={getStateColor(stateCode)}
                        stroke="#ffffff"
                        strokeWidth={0.5}
                        style={{
                          default: {
                            outline: "none",
                          },
                          hover: {
                            fill: isHovered ? "#1d4ed8" : getStateColor(stateCode),
                            outline: "none",
                            strokeWidth: 1,
                          },
                          pressed: {
                            outline: "none",
                          },
                        }}
                        onMouseEnter={() => setHoveredState(stateCode)}
                        onMouseLeave={() => setHoveredState(null)}
                      />
                    );
                  })
                }
              </Geographies>
            </ComposableMap>
            
            {/* Tooltip */}
            {hoveredState && (
              <div className="absolute top-4 left-4 bg-background border rounded-lg p-3 shadow-lg z-10">
                <div className="font-semibold">{stateNames[hoveredState] || hoveredState}</div>
                <div className="text-sm text-muted-foreground">
                  {getStateCount(hoveredState)} visitors
                </div>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 bg-slate-100 border rounded"></div>
                <span className="text-muted-foreground">0 visitors</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 bg-blue-200 rounded"></div>
                <span className="text-muted-foreground">Low</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 bg-blue-500 rounded"></div>
                <span className="text-muted-foreground">High ({maxCount})</span>
              </div>
            </div>
          </div>

          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t">
            <div className="text-center">
              <div className="text-lg font-semibold text-blue-600">
                {Object.keys(locationData.us_states).length}
              </div>
              <div className="text-xs text-muted-foreground">States Visited</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-semibold text-green-600">
                {Object.values(locationData.us_states).reduce((a, b) => a + b, 0)}
              </div>
              <div className="text-xs text-muted-foreground">US Visitors</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-semibold text-purple-600">
                {locationData.international}
              </div>
              <div className="text-xs text-muted-foreground">International</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-semibold text-orange-600">
                {locationData.local + locationData.unknown}
              </div>
              <div className="text-xs text-muted-foreground">Local/Unknown</div>
            </div>
          </div>

          {/* Top States */}
          {Object.keys(locationData.us_states).length > 0 && (
            <div className="pt-4 border-t">
              <h4 className="font-semibold mb-3 text-sm">Top States</h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(locationData.us_states)
                  .sort(([,a], [,b]) => b - a)
                  .slice(0, 6)
                  .map(([state, count]) => (
                    <div key={state} className="flex justify-between items-center text-sm">
                      <span className="font-medium">{stateNames[state] || state}</span>
                      <Badge variant="outline" className="text-xs">
                        {count}
                      </Badge>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default USHeatMap;
