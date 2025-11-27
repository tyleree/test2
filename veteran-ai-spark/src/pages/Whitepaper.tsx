import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Download, ArrowLeft, FileText, ExternalLink, AlertCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const Whitepaper = () => {
  const { toast } = useToast();
  const [pdfError, setPdfError] = useState(false);

  const downloadPDF = () => {
    // Open the PDF in a new tab for download
    window.open('/whitepaper.pdf', '_blank');
    toast({
      title: "Opening PDF",
      description: "The whitepaper PDF will open in a new tab",
    });
  };

  const downloadTeX = () => {
    // Download the LaTeX source
    const link = document.createElement('a');
    link.href = '/whitepaper.tex';
    link.download = 'veteran-ai-spark-whitepaper.tex';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast({
      title: "Downloading LaTeX Source",
      description: "The .tex file will be downloaded",
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Header Bar */}
      <div className="sticky top-0 z-50 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm border-b border-slate-200 dark:border-slate-700">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => window.history.back()}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={downloadTeX}>
              <FileText className="h-4 w-4 mr-2" />
              Download .tex
            </Button>
            <Button size="sm" onClick={downloadPDF}>
              <Download className="h-4 w-4 mr-2" />
              Download PDF
            </Button>
          </div>
        </div>
      </div>

      {/* PDF Viewer Container */}
      <div className="container mx-auto px-4 py-6">
        {/* Title Card */}
        <Card className="mb-6">
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-lg">
                <FileText className="h-8 w-8 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                  Technical Whitepaper
                </h1>
                <p className="text-slate-600 dark:text-slate-400">
                  Veteran AI Spark RAG System - Version 2.0
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* PDF Embed */}
        {!pdfError ? (
          <Card className="overflow-hidden">
            <div className="bg-slate-800 p-2 flex items-center justify-between">
              <span className="text-white text-sm font-medium px-2">
                whitepaper.pdf
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="text-white hover:text-white hover:bg-slate-700"
                onClick={() => window.open('/whitepaper.pdf', '_blank')}
              >
                <ExternalLink className="h-4 w-4 mr-1" />
                Open in New Tab
              </Button>
            </div>
            <iframe
              src="/whitepaper.pdf"
              className="w-full h-[85vh] border-0"
              title="Technical Whitepaper PDF"
              onError={() => setPdfError(true)}
            />
          </Card>
        ) : (
          /* Fallback if PDF doesn't exist */
          <Card>
            <CardContent className="p-12 text-center">
              <AlertCircle className="h-16 w-16 mx-auto text-amber-500 mb-4" />
              <h2 className="text-xl font-bold mb-2">PDF Not Yet Compiled</h2>
              <p className="text-slate-600 dark:text-slate-400 mb-6 max-w-md mx-auto">
                The whitepaper PDF needs to be compiled from the LaTeX source. 
                You can download the .tex file and compile it using Overleaf or a local LaTeX installation.
              </p>
              
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button variant="outline" onClick={downloadTeX}>
                  <FileText className="h-4 w-4 mr-2" />
                  Download .tex Source
                </Button>
                <Button
                  variant="outline"
                  onClick={() => window.open('https://www.overleaf.com/', '_blank')}
                >
                  <ExternalLink className="h-4 w-4 mr-2" />
                  Open Overleaf
                </Button>
              </div>
              
              <div className="mt-8 p-4 bg-slate-100 dark:bg-slate-800 rounded-lg text-left max-w-lg mx-auto">
                <h3 className="font-semibold mb-2">To compile the PDF:</h3>
                <ol className="text-sm text-slate-600 dark:text-slate-400 space-y-1 list-decimal list-inside">
                  <li>Download the .tex file</li>
                  <li>Upload to Overleaf or open in a LaTeX editor</li>
                  <li>Compile with pdflatex</li>
                  <li>Place the resulting PDF at <code className="bg-slate-200 dark:bg-slate-700 px-1 rounded">/public/whitepaper.pdf</code></li>
                </ol>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Footer */}
        <div className="text-center mt-8 text-sm text-slate-500 dark:text-slate-400">
          <p>Veteran AI Spark RAG System - Technical Whitepaper - November 2024</p>
          <p className="mt-1">OpenAI-Only Architecture with Intelligent Model Routing</p>
        </div>
      </div>
    </div>
  );
};

export default Whitepaper;
