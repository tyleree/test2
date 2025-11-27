import { useEffect } from "react";

const Whitepaper = () => {
  useEffect(() => {
    // Redirect directly to the PDF
    window.location.href = "/whitepaper.pdf";
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <p className="text-slate-600">Loading whitepaper...</p>
    </div>
  );
};

export default Whitepaper;
