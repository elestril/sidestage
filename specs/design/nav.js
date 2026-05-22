// Injects the top "DESIGN SPEC" bar on every mockup page.
//
// - When loaded inside an iframe, the banner is suppressed and `--nav-h`
//   is set to 0, so the iframe content uses its full viewport height.
// - On `main.html`, the bar also hosts the Playground controls (slot +
//   connected) and dispatches `designnav:change` CustomEvents that
//   main.html listens for to repoint the iframe.

const NAV_HEIGHT_PX = 26;

const PAGES = [
  { file: 'main.html',                  label: 'main' },
  { file: 'workspace.html',             label: 'workspace' },
  { file: 'scene_panel.html',           label: 'scene_panel' },
  { file: 'scene_bubble.html',          label: 'scene_bubble' },
  { file: 'character_panel.html',       label: 'character_panel' },
  { file: 'character_bubble.html',      label: 'character_bubble' },
  { file: 'message_item.html',          label: 'message_item' },
  { file: 'message_input.html',         label: 'message_input' },
  { file: 'state_loading.html',         label: 'state_loading' },
  { file: 'state_disconnected.html',    label: 'state_disconnected' },
  { file: 'state_unknown_entity.html',  label: 'state_unknown_entity' },
];

const PLAYGROUND_SLOTS = [
  { value: 'scene_panel',         label: 'scene_panel' },
  { value: 'character_panel',     label: 'character_panel' },
  { value: 'state_loading',       label: 'state_loading' },
  { value: 'state_unknown_entity',label: 'state_unknown_entity' },
];

(function () {
  const inIframe = window.self !== window.top;

  document.documentElement.style.setProperty('--nav-h', inIframe ? '0px' : NAV_HEIGHT_PX + 'px');
  if (inIframe) return;

  const here = (location.pathname.split('/').pop() || 'main.html');
  const isMain = here === 'main.html' || here === '' || here === '/';

  const SELECT_STYLE = `
    background: transparent;
    color: #e2e8f0;
    border: none;
    padding: 0 14px 0 0;
    font-family: inherit;
    font-size: 11px;
    line-height: 1;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    background-image: linear-gradient(45deg, transparent 50%, #94a3b8 50%), linear-gradient(135deg, #94a3b8 50%, transparent 50%);
    background-position: calc(100% - 8px) 50%, calc(100% - 4px) 50%;
    background-size: 4px 4px, 4px 4px;
    background-repeat: no-repeat;
    color-scheme: dark;
  `;
  const OPTION_STYLE = 'background-color: #0f172a; color: #e2e8f0;';

  const pageOptions = PAGES.map((p) => `
    <option value="${p.file}" ${p.file === here ? 'selected' : ''} style="${OPTION_STYLE}">${p.label}</option>
  `).join('');

  const playgroundHTML = isMain ? `
    <span style="opacity: 0.3;">|</span>
    <span style="color: #f59e0b; font-weight: 700; letter-spacing: 0.05em;">PLAYGROUND</span>
    <label style="display: flex; align-items: center; gap: 4px;">
      <span style="opacity: 0.6;">slot:</span>
      <select id="design-nav-slot" style="${SELECT_STYLE} border-bottom: 1px dotted #475569;">
        ${PLAYGROUND_SLOTS.map((s) => `<option value="${s.value}" style="${OPTION_STYLE}">${s.label}</option>`).join('')}
      </select>
    </label>
    <label style="display: flex; align-items: center; gap: 4px;">
      <span style="opacity: 0.6;">connected:</span>
      <input id="design-nav-connected" type="checkbox" checked style="accent-color: #10b981; cursor: pointer;" />
    </label>
  ` : '';

  const banner = document.createElement('div');
  banner.id = 'mockup-nav';
  banner.innerHTML = `
    <div style="
      box-sizing: border-box;
      height: ${NAV_HEIGHT_PX}px;
      background: #0f172a;
      color: #e2e8f0;
      padding: 0 8px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      line-height: 1;
      border-bottom: 2px solid #f59e0b;
    ">
      <span style="color: #f59e0b; font-weight: 700; letter-spacing: 0.05em;">◆ DESIGN</span>
      <span style="display: flex; align-items: center;">
        <span style="opacity: 0.6;">specs/design/</span><select id="design-nav-page" style="${SELECT_STYLE} border-bottom: 1px dotted #475569;">
          ${pageOptions}
        </select>
      </span>
      ${playgroundHTML}
    </div>
  `;

  document.body.insertBefore(banner, document.body.firstChild);

  banner.querySelector('#design-nav-page').addEventListener('change', (e) => {
    location.href = './' + e.target.value;
  });

  if (isMain) {
    const slotSel = banner.querySelector('#design-nav-slot');
    const connEl = banner.querySelector('#design-nav-connected');
    const emit = () => {
      document.dispatchEvent(new CustomEvent('designnav:change', {
        detail: { slot: slotSel.value, connected: connEl.checked },
      }));
    };
    slotSel.addEventListener('change', emit);
    connEl.addEventListener('change', emit);
  }
})();
