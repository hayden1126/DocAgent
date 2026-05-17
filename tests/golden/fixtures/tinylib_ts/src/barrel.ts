// Pure barrel — every export is a re-export. The discovery cascade must
// drop this module via the locked barrel-file rule (Plan 07-04).
export * from "./cli.js";
export * from "./types.js";
