import './ui/style.css';
import {App} from './ui/app';

const app = new App();
(window as unknown as {tower: App}).tower = app;
app.boot().catch(err => {
  document.body.insertAdjacentHTML('beforeend', `<p class="fatal">${err instanceof Error ? err.message : String(err)}</p>`);
});
