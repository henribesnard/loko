/**
 * Accessibility utilities (X2)
 * Implements PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
 */

/**
 * Announce message to screen readers.
 *
 * Uses aria-live region to announce dynamic content changes.
 *
 * @param message Message to announce
 * @param priority 'polite' (wait for pause) or 'assertive' (interrupt)
 */
export function announce(message: string, priority: 'polite' | 'assertive' = 'polite'): void {
  // Find or create aria-live region
  let liveRegion = document.getElementById('a11y-announcer');

  if (!liveRegion) {
    liveRegion = document.createElement('div');
    liveRegion.id = 'a11y-announcer';
    liveRegion.setAttribute('aria-live', priority);
    liveRegion.setAttribute('aria-atomic', 'true');
    liveRegion.className = 'sr-only'; // Visually hidden, screen reader only
    document.body.appendChild(liveRegion);
  }

  // Update priority if changed
  if (liveRegion.getAttribute('aria-live') !== priority) {
    liveRegion.setAttribute('aria-live', priority);
  }

  // Clear and set message (triggers announcement)
  liveRegion.textContent = '';
  setTimeout(() => {
    liveRegion!.textContent = message;
  }, 100);
}

/**
 * Trap focus within an element (for modals, dialogs).
 *
 * @param element Container element
 * @returns Cleanup function to remove trap
 */
export function trapFocus(element: HTMLElement): () => void {
  const focusableSelector = [
    'a[href]',
    'button:not([disabled])',
    'textarea:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ');

  const getFocusableElements = (): HTMLElement[] => {
    return Array.from(element.querySelectorAll(focusableSelector));
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return;

    const focusable = getFocusableElements();
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    // Shift+Tab on first element: go to last
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    }
    // Tab on last element: go to first
    else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  element.addEventListener('keydown', handleKeyDown);

  // Focus first element
  const focusable = getFocusableElements();
  if (focusable.length > 0) {
    focusable[0].focus();
  }

  // Cleanup
  return () => {
    element.removeEventListener('keydown', handleKeyDown);
  };
}

/**
 * Restore focus to a saved element.
 *
 * Usage:
 *   const restore = saveFocus();
 *   // ... open modal ...
 *   restore(); // Returns focus to original element
 */
export function saveFocus(): () => void {
  const activeElement = document.activeElement as HTMLElement;

  return () => {
    if (activeElement && typeof activeElement.focus === 'function') {
      activeElement.focus();
    }
  };
}

/**
 * Check if element is visible to screen readers.
 */
export function isAccessible(element: HTMLElement): boolean {
  // Check aria-hidden
  if (element.getAttribute('aria-hidden') === 'true') {
    return false;
  }

  // Check display/visibility
  const style = window.getComputedStyle(element);
  if (style.display === 'none' || style.visibility === 'hidden') {
    return false;
  }

  return true;
}

/**
 * Add screen-reader-only CSS class.
 *
 * Element is visually hidden but accessible to screen readers.
 *
 * CSS (add to index.css):
 *   .sr-only {
 *     position: absolute;
 *     width: 1px;
 *     height: 1px;
 *     padding: 0;
 *     margin: -1px;
 *     overflow: hidden;
 *     clip: rect(0, 0, 0, 0);
 *     white-space: nowrap;
 *     border-width: 0;
 *   }
 */
export const SR_ONLY_CLASS = 'sr-only';
