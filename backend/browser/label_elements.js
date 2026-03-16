(function() {
  // Remove red-number overlay divs from any previous labeling run
  document.querySelectorAll('.visual-agent-label').forEach(el => el.remove());

  // CRITICAL: Clear all stale data-visual-agent-id attributes from every element in the
  // DOM before assigning new IDs. Without this, elements that were labeled in a
  // previous round (e.g. dropdown <li> items that are now hidden) keep their old IDs.
  // When the same numeric ID is re-assigned to a different element in the next round,
  // Playwright finds 2 matches for the same selector and times out on the wrong one.
  document.querySelectorAll('[data-visual-agent-id]').forEach(el => {
    el.removeAttribute('data-visual-agent-id');
    el.removeAttribute('data-visual-agent-label');
    el.removeAttribute('data-visual-agent-name');
    el.removeAttribute('data-visual-agent-placeholder');
    el.removeAttribute('data-visual-agent-type');
    el.removeAttribute('data-visual-agent-role');
    el.removeAttribute('data-visual-agent-tag');
    el.removeAttribute('data-visual-agent-required');
  });

  function normalizeText(value) {
    return (value || '').replace(/\s+/g, ' ').trim();
  }

  function getAssociatedLabelText(el) {
    const ariaLabel = normalizeText(el.getAttribute('aria-label'));
    if (ariaLabel) return ariaLabel;

    const ariaLabelledBy = el.getAttribute('aria-labelledby');
    if (ariaLabelledBy) {
      const labelledEl = document.getElementById(ariaLabelledBy);
      const labelledText = normalizeText(labelledEl ? labelledEl.textContent : '');
      if (labelledText) return labelledText;
    }

    const wrappedLabel = el.closest('label');
    const wrappedText = normalizeText(wrappedLabel ? wrappedLabel.textContent : '');
    if (wrappedText) return wrappedText;

    const id = el.getAttribute('id');
    if (id) {
      const forLabel = document.querySelector('label[for="' + id.replace(/"/g, '\\"') + '"]');
      const forText = normalizeText(forLabel ? forLabel.textContent : '');
      if (forText) return forText;
    }

    const placeholder = normalizeText(el.getAttribute('placeholder'));
    if (placeholder) return placeholder;

    return '';
  }

  function isInViewport(rect) {
    return rect.right > 0 &&
           rect.left < window.innerWidth &&
           rect.bottom > 0 &&
           rect.top < window.innerHeight;
  }

  function isAuthPlaceholder(el) {
    const className = (el.className && typeof el.className === 'string') ? el.className : '';
    if (!className.toLowerCase().includes('placeholder')) return false;
    const ariaLabel = normalizeText(el.getAttribute('aria-label') || '');
    const role = (el.getAttribute('role') || '').toLowerCase();
    const authPattern = /continue with|sign in with|log in with|google|facebook|apple|microsoft|linkedin/i;
    return role === 'button' || authPattern.test(ariaLabel);
  }

  const interactiveSelectors = [
    'a', 'button', 'input', 'textarea', 'select',
    '[role="button"]', '[role="link"]', '[role="menuitem"]',
    '[role="option"]',    // dropdown list items (e.g. "One way", "Round trip")
    '[role="radio"]',     // radio button groups (trip type selector)
    '[role="checkbox"]',  // checkbox controls
    '[role="tab"]',       // tab controls
    '[role="switch"]',    // toggle switches
    '[role="listitem"][tabindex]', // focusable list items
    '[onclick]', '[tabindex="0"]'
  ];

  const elements = Array.from(document.querySelectorAll(interactiveSelectors.join(',')))
    .filter(el => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      const opacity = parseFloat(style.opacity);
      return rect.width > 0 &&
             rect.height > 0 &&
             style.visibility !== 'hidden' &&
             style.display !== 'none' &&
             !isNaN(opacity) && opacity > 0.01 &&
             isInViewport(rect) &&
             !isAuthPlaceholder(el);
    });

  elements.forEach((el, index) => {
    const id = index + 1;
    const rect = el.getBoundingClientRect();
    const tagName = normalizeText(el.tagName).toLowerCase();
    const typeAttr = normalizeText(el.getAttribute('type')) || (el.type ? normalizeText(el.type) : '');
    const nameAttr = normalizeText(el.getAttribute('name'));
    const placeholderAttr = normalizeText(el.getAttribute('placeholder'));
    const roleAttr = normalizeText(el.getAttribute('role'));
    const requiredAttr = el.required || el.getAttribute('aria-required') === 'true' ? 'true' : 'false';

    const label = document.createElement('div');
    label.className = 'visual-agent-label';
    label.textContent = id.toString();
    Object.assign(label.style, {
      position: 'absolute',
      left: (rect.left + window.scrollX) + 'px',
      top: (rect.top + window.scrollY) + 'px',
      background: '#ff0000',
      color: 'white',
      padding: '2px 4px',
      fontSize: '12px',
      fontWeight: 'bold',
      zIndex: '10000',
      borderRadius: '2px',
      pointerEvents: 'none',
      boxShadow: '0 1px 2px rgba(0,0,0,0.2)'
    });

    document.body.appendChild(label);
    el.setAttribute('data-visual-agent-id', id.toString());
    const labelText = getAssociatedLabelText(el);
    if (labelText) el.setAttribute('data-visual-agent-label', labelText);
    if (nameAttr) el.setAttribute('data-visual-agent-name', nameAttr);
    if (placeholderAttr) el.setAttribute('data-visual-agent-placeholder', placeholderAttr);
    if (typeAttr) el.setAttribute('data-visual-agent-type', typeAttr);
    if (roleAttr) el.setAttribute('data-visual-agent-role', roleAttr);
    if (tagName) el.setAttribute('data-visual-agent-tag', tagName);
    el.setAttribute('data-visual-agent-required', requiredAttr);
  });

  return elements.length;
})();
