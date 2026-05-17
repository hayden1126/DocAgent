export interface Greeting {
  who: string;
}

export type Salutation = "hi" | "hello";

export enum Tone {
  Warm,
  Cool,
}

export class Greeter {
  constructor(private readonly tone: Tone = Tone.Warm) {}

  greet(name: string): string {
    const prefix = this.tone === Tone.Warm ? "hello" : "hi";
    return `${prefix}, ${name}`;
  }
}

export function makeGreeting(who: string): Greeting {
  return { who };
}
