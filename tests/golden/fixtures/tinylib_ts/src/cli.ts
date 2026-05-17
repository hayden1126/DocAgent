import { Greeter, Tone } from "./index.js";

export function greet(name: string = "world"): void {
  const g = new Greeter(Tone.Warm);
  console.log(g.greet(name));
}
