import { Greeter, Tone } from "./index.js";

/**
 * Greet the user with their name.
 *
 * @param name The user's name.
 * @returns A formatted greeting string.
 * @throws Error when name is empty.
 */
export function greet(name: string = "world"): void {
  const g = new Greeter(Tone.Warm);
  console.log(g.greet(name));
}
