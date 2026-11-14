"""A quiet, single-thread agent interface with an anchored composer."""

CSS = """
body, .gradio-container { background: #faf9f6 !important; color: #282824; }
.gradio-container { max-width: 1100px !important; width: 100% !important;
 box-sizing: border-box !important; padding: 12px 24px 20px !important;
 margin-inline: auto !important; }
.gradio-container .main { padding-inline: 0 !important; }
#topbar { align-items: center; border-bottom: 1px solid #e7e5df;
 padding: 8px 0 16px; margin-bottom: 20px; }
.wordmark { font-size: 14px; color: #32322f; letter-spacing: -.02em; }
.wordmark span { color: #96938a; margin-left: 8px; font-size: 13px; }
#topbar button { background: transparent; border-color: #dfddd6; }
#chat-thread, #composer-shell { max-width: 820px; width: 100%; margin: 0 auto;
 box-sizing: border-box; min-width: 0 !important; }
#chat-thread { min-height: 48vh; padding: 12px 8px 30px; gap: 20px; }
#welcome { padding: 72px 16px 60px; text-align: center; color: #77756d; }
.agent-mark { font-size: 36px; color: #b47754; margin-bottom: 18px; }
#welcome h1 { font: 400 clamp(28px, 4vw, 38px) Georgia, serif;
 letter-spacing: -.035em; color: #37352f; margin-bottom: 14px; }
#welcome p { font-size: 15px; line-height: 1.7; }
.chat-event { min-width: 0 !important; min-height: 0 !important;
 flex: 0 0 auto !important; height: auto !important;
 gap: 6px !important; padding: 12px 0; }
.chat-event > .block { flex: 0 0 auto !important; min-height: 0 !important; }
.chat-event p, .chat-event li { font-size: 14px; line-height: 1.75; }
.speaker p { font-size: 11px !important; font-weight: 600; color: #868277;
 letter-spacing: .02em; margin-bottom: 4px; }
.from-user { background: #efede7; border-radius: 16px; padding: 10px 16px;
 margin-left: auto; max-width: min(88%, 42rem); width: fit-content !important; }
.from-user .prose p { margin: 0; }
.from-assistant { padding-right: 18px; }
.event-report, .event-parameters, .event-input_form { border: 1px solid #e4e1d9;
 background: #fff; border-radius: 14px; padding: 18px; }
.event-input_form { gap: 14px !important; }
.input-form-title p { font-size: 17px !important; font-weight: 600; margin: 0; }
.input-form-description p { color: #77736a; margin: 0; }
.input-form-hint p { font-size: 11px !important; color: #928d82; margin: 0; }
.input-form-error p { color: #a33d32; font-size: 13px !important; }
.report-saved { background: #eff5ef; color: #365b40; border-radius: 8px;
 padding: 8px 12px !important; }
.report-saved p { margin: 0; font-size: 13px !important; font-weight: 500; }
.report-approval { align-items: center; gap: 12px; margin-top: 8px; }
.report-approval > .block { min-width: 0 !important; }
.report-approval button { border-radius: 8px; min-height: 36px; }
.data-review { border-top: 1px solid #edeae3; margin-top: 10px; }
.data-review > summary { cursor: pointer; display: flex; align-items: center;
 gap: 12px; padding: 14px 2px; font-size: 13px; font-weight: 500;
 list-style: none; }
.data-review > summary::after { content: '⌄'; margin-left: auto; color: #8d877c; }
.data-review[open] > summary::after { content: '⌃'; }
.review-count { font-size: 11px; color: #918a7e; font-weight: 400; }
.data-review-body { padding: 0 2px 8px; }
.review-query + .review-query { border-top: 1px solid #edeae3;
 padding-top: 14px; margin-top: 14px; }
.review-source-row { display: flex; flex-wrap: wrap; gap: 8px 14px;
 align-items: baseline; padding: 0 0 12px; }
.review-source-row strong { font-size: 13px; font-weight: 600; }
.review-source-row span { color: #847d71; font-size: 12px; overflow-wrap: anywhere; }
.review-facts { margin: 0; display: grid; gap: 8px; }
.review-facts > div { display: grid; grid-template-columns: 116px minmax(0, 1fr);
 gap: 12px; font-size: 12px; line-height: 1.6; }
.review-facts dt { color: #91897c; font-weight: 400; }
.review-facts dd { margin: 0; color: #49453d; overflow-wrap: anywhere; }
.review-query-label { margin: 12px 0 6px; color: #91897c; font-size: 11px; }
.review-sql, .review-technical pre { background: #f6f5f1;
 padding: 12px 14px; border-radius: 8px; font: 12px/1.7 ui-monospace, monospace;
 white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; overflow: auto;
 margin: 0; }
.review-sql code { background: none !important; padding: 0 !important;
 font: inherit; }
.review-inputs { margin-top: 16px; padding-top: 12px; border-top: 1px solid #edeae3; }
.review-inputs h4 { font-size: 11px; color: #91897c; font-weight: 500;
 margin: 0 0 8px; }
.review-empty { color: #91897c; font-size: 11px !important; margin: 12px 0 0; }
.review-technical { margin-top: 14px; }
.review-technical summary { cursor: pointer; color: #91897c; font-size: 11px;
 margin-bottom: 8px; }
.data-review summary:focus-visible { outline: 2px solid #a0795b; outline-offset: 3px; }
.event-input_form > button { align-self: flex-end; min-width: 116px !important;
 width: auto !important; border-radius: 9px; }
.event-report button, .event-report a { text-align: left; }
.event-activity { padding: 2px 0; }
.activity-line p { font-size: 12px !important; color: #8a867a; }
#composer-shell { position: sticky; bottom: 10px; z-index: 5;
 background: #fff; border: 1px solid #dedbd3; border-radius: 20px;
 padding: 10px 14px 6px; box-shadow: 0 5px 24px #3932220a; gap: 4px; }
#composer { border: none !important; background: white !important;
 padding: 2px 0 !important; box-shadow: none; }
#composer textarea { background: transparent; border: 0; box-shadow: none;
 font-size: 15px; padding: 6px 2px; background-color: white !important; }
#starter-buttons { gap: 6px; }
#starter-buttons button, #attach-toggle, #saved-toggle {
 flex: 0 0 auto !important; width: auto !important;
 min-width: max-content !important; white-space: nowrap; }
.gradio-container:has(.event-message) #starter-buttons { display: none; }
#starter-buttons button { background: #f5f4ef; border: 0; min-height: 30px;
 font-size: 12px; font-weight: 400; }
#composer-toolbar { align-items: center; gap: 6px; flex-wrap: nowrap; }
#composer-toolbar button { height: 36px; min-height: 36px;
 font-size: 12px; line-height: 1; white-space: nowrap; }
#attach-toggle, #saved-toggle { background: transparent; border: 0;
 box-shadow: none; color: #77736a; padding: 0 10px; }
#attach-toggle:hover, #saved-toggle:hover { background: #f2f0e9; }
#toolbar-spacer { flex: 1 !important; min-width: 0 !important; }
#send { width: 76px !important; min-width: 76px !important;
 border-radius: 9px; padding: 0 16px; font-weight: 500; }
#attach-popover, #saved-popover { position: absolute; bottom: calc(100% + 10px);
 left: 0; width: min(360px, 100%) !important; min-width: 0 !important;
 box-sizing: border-box; border: 1px solid #dedbd3; border-radius: 14px;
 background: white; padding: 16px; z-index: 12;
 box-shadow: 0 8px 30px #39322218; gap: 10px; }
#attach-popover button, #saved-popover button { min-height: 34px;
 font-size: 12px; border-radius: 8px; }
#attach-popover p, #saved-popover p { font-size: 13px; }
#dismiss-menus { display: none !important; }
#privacy { color: #aaa69b; text-align: center; font-size: 10px; }
button { transition: background .15s ease, transform .15s ease; }
button:active:not(:disabled) { transform: translateY(1px); }
button:focus-visible, a:focus-visible, textarea:focus-visible {
 outline: 2px solid #a0795b !important; outline-offset: 3px; }
button:disabled { opacity: .45; }
@media (max-width: 600px) {
 .gradio-container { padding: 8px 12px !important; }
 #chat-thread { padding: 0 0 16px; }
 #composer-shell { padding: 10px; bottom: 4px; }
 .from-user { max-width: 94%; }
 .event-report, .event-parameters, .event-input_form { padding: 12px; }
 #welcome { padding: 48px 0; }
}
@media (prefers-reduced-motion: reduce) { button { transition: none; } }
"""

JS = """() => {
 const dismiss = () => {
   const opened = ['attach-popover', 'saved-popover'].some(id =>
     document.getElementById(id)?.getClientRects().length);
   if (opened) document.getElementById('dismiss-menus')?.click();
 };
 document.addEventListener('pointerdown', (event) => {
   if (!event.target.closest(
       '#attach-popover, #saved-popover, #attach-toggle, #saved-toggle')) dismiss();
 });
 document.addEventListener('keydown', (event) => {
   if (event.key === 'Escape') dismiss();
   if (event.target.matches('#composer textarea') && event.key === 'Enter'
       && !event.shiftKey && !event.isComposing) {
     event.preventDefault();
     const send = document.getElementById('send');
     if (send && !send.disabled) send.click();
   }
 });
 let follow = true;
 window.addEventListener('scroll', () => {
   follow = window.innerHeight + window.scrollY >= document.body.scrollHeight - 240;
 }, {passive:true});
 const thread = document.getElementById('chat-thread');
 if (thread) new MutationObserver(() => {
   if (follow && !document.getElementById('welcome')) requestAnimationFrame(() =>
     window.scrollTo(0, document.body.scrollHeight));
 }).observe(thread, {childList:true, subtree:true, characterData:true});
} """


def launch_options():
    import gradio as gr

    theme = gr.themes.Soft(
        primary_hue="stone",
        neutral_hue="stone",
        font=["Avenir Next", "Segoe UI", "Arial", "sans-serif"],
    ).set(
        body_background_fill="#faf9f6",
        body_background_fill_dark="#faf9f6",
        body_text_color="#282824",
        body_text_color_dark="#282824",
        block_background_fill="#fff",
        block_background_fill_dark="#fff",
        input_background_fill="#fff",
        input_background_fill_dark="#fff",
        button_primary_background_fill="#33332f",
        button_primary_background_fill_hover="#191917",
        button_primary_background_fill_dark="#33332f",
        button_primary_text_color="white",
        button_primary_text_color_dark="white",
    )
    return {"theme": theme, "css": CSS, "js": JS, "footer_links": []}
