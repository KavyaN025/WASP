/**
 * WASP Network Lab - Shared Utility Functions
 * Strict Rule: NO EMOJIS anywhere.
 */

const WaspUtils = {
  // Format numbers to fixed decimals
  formatNum: function(num, decimals = 3) {
    if (num === undefined || num === null) return "-";
    return Number(num).toFixed(decimals);
  },

  // LaTeX to formatted string helper
  formatFormula: function(eq, sub, val) {
    return {
      equation: eq,
      substitution: sub,
      result: val
    };
  },

  // Calculate posterior confidence P_L(c) = alpha / (alpha + beta)
  calcConfidence: function(alpha, beta) {
    const denom = alpha + beta;
    return denom > 0 ? alpha / denom : 0.1;
  },

  // Color classes for risk levels
  getRiskBadgeClass: function(level) {
    if (level === "High") return "badge badge-high";
    if (level === "Medium") return "badge badge-medium";
    return "badge badge-low";
  },

  // Color classes for protection modes
  getModeColor: function(mode) {
    if (mode === "Shielded") return "var(--color-danger)";
    if (mode === "Protected") return "var(--color-warning)";
    return "var(--color-teal)";
  }
};

window.WaspUtils = WaspUtils;
