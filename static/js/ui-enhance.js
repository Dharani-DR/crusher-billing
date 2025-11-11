// Drawer toggle for mobile bottom nav
document.addEventListener('click', (e) => {
	const btn = e.target.closest('[data-toggle="glass-drawer"]');
	if (btn) {
		const sidebar = document.getElementById('appSidebar');
		if (!sidebar) return;
		const isHidden = sidebar.classList.contains('hidden');
		if (isHidden) sidebar.classList.remove('hidden');
		else sidebar.classList.add('hidden');
	}
});

// Tamil font size toggles
const root = document.documentElement;
const fontInc = document.getElementById('fontInc');
const fontDec = document.getElementById('fontDec');
let baseFontScale = 1;
function applyFontScale() {
	root.style.fontSize = `${Math.max(0.85, Math.min(1.25, baseFontScale))}rem`;
}
if (fontInc) fontInc.addEventListener('click', () => { baseFontScale += 0.05; applyFontScale(); });
if (fontDec) fontDec.addEventListener('click', () => { baseFontScale -= 0.05; applyFontScale(); });

// Print auto-trigger helper for invoice route
if (window.location.pathname.includes('/invoice/') && window.location.search.includes('print=1')) {
	window.addEventListener('load', () => {
		setTimeout(() => window.print(), 1000);
	});
}

// Vehicle regex available globally
window.vehicleRegex = /^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$/i;

// Toast helper (minimal)
window.toast = function(message, type = 'info') {
	const el = document.createElement('div');
	el.className = `fixed bottom-4 right-4 z-50 rounded-md border px-4 py-2 text-sm ${
		type === 'success' ? 'border-emerald-700 bg-emerald-900/30 text-emerald-200' :
		type === 'error' ? 'border-rose-700 bg-rose-900/30 text-rose-200' :
		'border-slate-600 bg-slate-800/40 text-slate-200'
	}`;
	el.textContent = message;
	document.body.appendChild(el);
	setTimeout(() => { el.remove(); }, 3000);
};


