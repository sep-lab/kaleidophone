# Bundled fonts

All five are [SIL Open Font License 1.1](licenses/); the full licence text for
each is in `licenses/`. They are redistributed here, unmodified, as the OFL
permits.

| File | Family | Why it's here |
|---|---|---|
| `Vazirmatn-Variable.ttf` | [Vazirmatn](https://github.com/rastikerdar/vazirmatn) | Persian/Arabic. Weight axis 100–900. |
| `SpaceGrotesk-Variable.ttf` | [Space Grotesk](https://github.com/floriankarsten/space-grotesk) | Display type. Weight axis 300–700. |
| `SpaceMono-Regular.ttf` | [Space Mono](https://github.com/googlefonts/spacemono) | The machine-readout voice. |
| `SpaceMono-Bold.ttf` | Space Mono | |
| `CourierPrime-Regular.ttf` | [Courier Prime](https://github.com/quoteunquoteapps/CourierPrime) | Subtitle/typewriter. |

## Why these ship in the repo rather than being resolved from the system

A font referenced by system path (`/usr/share/fonts/truetype/...`) renders on
exactly one machine, and silently renders *differently* on any other. This
project's central promise is that the same brief produces the same output every
time — a font that might not be there, or might be a different version, breaks
that promise in a way that is invisible until you compare two renders side by
side.

672 KB total, against the 10 MB tracked-files ceiling in
`.github/workflows/scripts/check_repo_size.sh`. `.ttf` is not a blocked
extension: `check_no_media.sh` blocks audio, video and images, because those
are the formats that carry someone's copyrighted work or likeness. A libre
font carries neither — see
[ADR-0003](../../../../docs/decisions/0003-public-framework-private-assets.md).

A brief can still point at any other font with `font: "path:/your/font.ttf"`.
