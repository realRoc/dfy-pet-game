import {defineConfig} from 'vite';
import {viteSingleFile} from 'vite-plugin-singlefile';

// One self-contained index.html, so the build opens by double-click with no server.
export default defineConfig({
  base: './',
  plugins: [viteSingleFile()],
  build: {assetsInlineLimit: 100_000_000},
});
