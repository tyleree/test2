# Hosting Performance Guide

## Static Asset Optimization

### Enable Compression
Ensure your hosting provider enables:
- **Brotli compression** (preferred, ~20% better than gzip)
- **Gzip compression** (fallback)

### Cache Headers
Set long cache times for hashed assets:
```
# Hashed assets (JS/CSS with hash in filename)
/assets/*.js    Cache-Control: max-age=31536000, immutable
/assets/*.css   Cache-Control: max-age=31536000, immutable

# HTML files
/*.html         Cache-Control: max-age=0, must-revalidate

# Images and fonts  
/*.svg          Cache-Control: max-age=31536000
/*.woff2        Cache-Control: max-age=31536000
```

### Recommended Hosting
- **Netlify**: Auto-enables Brotli, optimal headers
- **Vercel**: Built-in performance optimizations
- **Cloudflare**: CDN + compression + caching
- **AWS S3 + CloudFront**: Manual config needed

### Testing
- Use Lighthouse to verify Core Web Vitals
- Check compression: `curl -H "Accept-Encoding: br,gzip" -I https://yoursite.com/assets/index-[hash].js`
