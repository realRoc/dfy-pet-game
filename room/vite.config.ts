import {defineConfig} from 'vite';
import {viteSingleFile} from 'vite-plugin-singlefile';

// One self-contained index.html: the pet serves it from content/room/ on 127.0.0.1.
// In dev, point ROOM_API at a running pet's room server (its port is in the URL the pet opens):
//   ROOM_API=http://127.0.0.1:54321 npm run dev   then open http://localhost:5173/?t=<token>
const api = process.env.ROOM_API;
export default defineConfig({
  base: './',
  plugins: [viteSingleFile()],
  build: {assetsInlineLimit: 100_000_000},
  server: api ? {proxy: {'/api': {target: api, changeOrigin: true}, '/character': {target: api, changeOrigin: true}}} : {},
});
