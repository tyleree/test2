import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'

function setFavicon(href: string) {
    try {
        const existing = document.querySelector("link[rel='icon']") as HTMLLinkElement | null;
        const link: HTMLLinkElement = existing || document.createElement('link');
        link.rel = 'icon';
        link.type = 'image/svg+xml';
        link.href = href;
        if (!existing) document.head.appendChild(link);
    } catch {}
}

setFavicon('/logo.svg');

createRoot(document.getElementById("root")!).render(<App />);
