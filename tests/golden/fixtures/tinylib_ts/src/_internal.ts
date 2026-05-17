/**
 * Internal helper for the tinylib_ts fixture.
 *
 * This module exists to exercise the private-filter rule in
 * `docagent.artifacts._ts_module_discovery`: every exported symbol's leaf
 * name starts with `_`, so the discovery cascade must drop this module
 * entirely.
 */
export function _internalHelper(): string {
  return "x";
}

export const _PRIVATE_CONST = 42;
