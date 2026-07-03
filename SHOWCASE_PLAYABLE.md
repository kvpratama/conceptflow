# Evolution

ConceptFlow was built incrementally. To make the impact of each change visible,
two fixed prompts — *"What is a neural network?"* and *"What is a Fourier
series?"* — were re-rendered at each milestone. The videos below show how output
quality progressed as new capabilities landed.

> **Note:** every video below is currently a placeholder using the #16 render.
> Replace each `user-attachments` URL with the matching milestone's playable URL.

## [#2 Proof of concept](https://github.com/kvpratama/conceptflow/pull/2)

Root agent + Manim render in a Modal sandbox; single monolithic video.

**What is a neural network?**

https://github.com/user-attachments/assets/214e4340-4018-4a0a-964f-265914d45090

**What is a Fourier series?**

https://github.com/user-attachments/assets/b2c262e4-b2b3-4d0b-9ca7-6da9b245be3d

## [#4 Filesystem backend](https://github.com/kvpratama/conceptflow/pull/4)

Shared per-thread workspace; `script.md` and `scene.py` persisted between agents.

**What is a neural network?**

https://github.com/user-attachments/assets/e4b75f65-7189-4109-92ce-8df97e00184b

**What is a Fourier series?**

https://github.com/user-attachments/assets/52be32b6-1c85-49c5-8ced-f6a02d0d3e60

## [#6 Agent skills](https://github.com/kvpratama/conceptflow/pull/6)

Per-agent `SKILL.md` guidance; script split into multiple scenes.

**What is a neural network?**

https://github.com/user-attachments/assets/5ec728c1-e082-4580-8b4f-a8e7fcd99f51

**What is a Fourier series?**

https://github.com/user-attachments/assets/a4527e7e-3245-4bbc-8620-a67ebc01f79f

## [#8 Voiceover](https://github.com/kvpratama/conceptflow/pull/8)

gTTS/pyttsx3 narration synced to each scene.

**What is a neural network?**

https://github.com/user-attachments/assets/d44bd476-ecf2-4de3-9e2c-b762e011b01d

**What is a Fourier series?**

https://github.com/user-attachments/assets/18188100-acc6-4f97-b43e-4f62027da74d

## [#13 Shared sandbox](https://github.com/kvpratama/conceptflow/pull/13)

One reused Modal sandbox per subagent run; faster, more reliable renders.

**What is a neural network?**

https://github.com/user-attachments/assets/2b2a419c-a5f5-4b76-9033-deee11503b6a

**What is a Fourier series?**

https://github.com/user-attachments/assets/8e35519f-5f19-4148-9280-b1ebf5acfa07

## [#14 QA agent](https://github.com/kvpratama/conceptflow/pull/14)

Vision-LLM review of rendered scenes for visual defects (`qa.json`).

**What is a neural network?**

https://github.com/user-attachments/assets/72390d38-863c-488b-bdcc-a8ac266d006a

**What is a Fourier series?**

https://github.com/user-attachments/assets/793c1af6-11f3-46a6-adfc-2fbe5ebf5c71

## [#16 Research agent](https://github.com/kvpratama/conceptflow/pull/16)

Tavily + Wikipedia grounding before scripting (`research.md`).

**What is a neural network?**

https://github.com/user-attachments/assets/26a368dc-5699-4272-89fd-0ae04a076331

**What is a Fourier series?**

https://github.com/user-attachments/assets/032ec67c-8cee-4502-b69a-9e822889ce2b
