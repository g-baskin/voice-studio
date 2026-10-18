# Natural Voice benchmark

Standard measures: **OVRL / SIG / BAK** = Microsoft DNSMOS predicted listener ratings (1-5), **PESQ** = ITU-T P.862.2 wideband (1-4.6), **STOI** = intelligibility (0-1). Own measures: **echo** = level in pauses (dB, lower is better), **metal** = persistent ringing peaks (dB, lower is better). Averaged over the voices tested. Best value per row in bold.

## Overall (all damaged cases)

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal | speed (x real time) |
|---|---|---|---|---|---|---|---|---|
| untouched | 2.632 | 3.001 | 3.483 | 2.539 | 0.839 | -61.728 | 3.008 | 0 |
| classic (before AI) | 2.557 (-0.08) | 2.889 (-0.11) | 3.516 (+0.03) | 2.499 (-0.04) | 0.861 (+0.02) | -68.178 (-6.45) | 1.798 (-1.21) | 0.062 |
| AI cleanup only | 2.803 (+0.17) | 3.165 (+0.16) | 3.734 (+0.25) | 2.444 (-0.10) | 0.845 (+0.01) | -67.589 (-5.86) | 3.036 (+0.03) | 0.199 |
| app: standard | 2.806 (+0.17) | 3.127 (+0.13) | 3.797 (+0.31) | 2.448 (-0.09) | 0.863 (+0.02) | -70.644 (-8.92) | 1.886 (-1.12) | 0.25 |
| app: strong | 2.794 (+0.16) | 3.102 (+0.10) | 3.815 (+0.33) | 2.446 (-0.09) | 0.864 (+0.03) | -72.1 (-10.37) | 1.563 (-1.45) | 0.252 |

## By problem

### clean (no-harm check)

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal |
|---|---|---|---|---|---|---|---|
| untouched | 3.407 | 3.623 | 4.17 | 4.64 | 1 | -77.7 | 2.153 |
| classic (before AI) | 3.327 | 3.573 | 4.103 | 4.483 | 0.982 | -78 | 0.953 |
| AI cleanup only | 3.363 | 3.587 | 4.15 | 4.303 | 0.988 | -81.2 | 2.523 |
| app: standard | 3.37 | 3.59 | 4.147 | 4.353 | 0.987 | **-81.367** | 1.003 |
| app: strong | 3.377 | 3.593 | 4.15 | 4.33 | 0.986 | -81.1 | **0.347** |

### small room echo

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal |
|---|---|---|---|---|---|---|---|
| untouched | 2.187 | 2.677 | 3.287 | 1.233 | 0.674 | -59.133 | 3.713 |
| classic (before AI) | 2.173 | 2.56 | 3.413 | **1.283** | **0.747** | -74.967 | 2.68 |
| AI cleanup only | 2.41 | **2.817** | 3.577 | 1.237 | 0.688 | -63.667 | 3.837 |
| app: standard | **2.453** | 2.813 | **3.673** | 1.267 | 0.735 | -71.7 | 2.817 |
| app: strong | 2.39 | 2.75 | 3.637 | 1.27 | 0.739 | **-76.033** | **2.583** |

### big hall echo

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal |
|---|---|---|---|---|---|---|---|
| untouched | 1.55 | 2.247 | 1.963 | 1.107 | 0.73 | -31.5 | 3.367 |
| classic (before AI) | 1.593 | 2.113 | 2.397 | 1.153 | 0.767 | -38.833 | 1.793 |
| AI cleanup only | 2.23 | **2.93** | 3.01 | 1.163 | 0.765 | -43.667 | 3.37 |
| app: standard | 2.333 | 2.853 | 3.293 | 1.21 | 0.794 | -47.667 | 2.11 |
| app: strong | **2.363** | 2.833 | **3.4** | **1.217** | **0.796** | **-49.967** | **1.757** |

### metallic (phase loss)

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal |
|---|---|---|---|---|---|---|---|
| untouched | 3.257 | 3.503 | 4.117 | 3.4 | 0.983 | -75.767 | 2.173 |
| classic (before AI) | 3.207 | 3.477 | 4.063 | 3.277 | 0.967 | -75.533 | 0.863 |
| AI cleanup only | 3.25 | 3.49 | 4.113 | 3.22 | 0.971 | -79.633 | 2.147 |
| app: standard | 3.25 | 3.493 | 4.11 | 3.153 | 0.971 | **-79.9** | 0.83 |
| app: strong | 3.25 | 3.497 | 4.11 | 3.163 | 0.97 | -79.733 | **0.247** |

### ringing resonances

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal |
|---|---|---|---|---|---|---|---|
| untouched | 3.4 | 3.62 | 4.157 | 4.64 | 0.998 | -77.533 | 3.19 |
| classic (before AI) | 3.3 | 3.56 | 4.077 | 4.403 | 0.981 | -78.3 | 1.593 |
| AI cleanup only | 3.383 | 3.603 | 4.143 | 4.337 | 0.987 | -81.1 | 3.083 |
| app: standard | 3.36 | 3.59 | 4.137 | 4.23 | 0.984 | -81.533 | 1.737 |
| app: strong | 3.367 | 3.593 | 4.143 | 4.197 | 0.984 | **-81.567** | **1.143** |

### low-bitrate codec

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal |
|---|---|---|---|---|---|---|---|
| untouched | 3.383 | 3.607 | 4.15 | 3.687 | 0.992 | -76 | 1.797 |
| classic (before AI) | 3.327 | 3.567 | 4.117 | 3.647 | 0.975 | -76.267 | 1.05 |
| AI cleanup only | 3.357 | 3.58 | 4.143 | 3.507 | 0.98 | -80.267 | 1.917 |
| app: standard | 3.35 | 3.577 | 4.143 | 3.577 | 0.979 | **-80.433** | 0.977 |
| app: strong | 3.343 | 3.577 | 4.137 | 3.583 | 0.978 | -80.267 | **0.96** |

### typical AI ad (all)

| Method | OVRL | SIG | BAK | PESQ | STOI | echo | metal |
|---|---|---|---|---|---|---|---|
| untouched | 2.013 | 2.35 | 3.223 | 1.17 | 0.659 | -50.433 | 3.807 |
| classic (before AI) | 1.74 | 2.057 | 3.03 | 1.23 | **0.73** | **-65.167** | 2.81 |
| AI cleanup only | **2.187** | **2.57** | 3.417 | 1.203 | 0.68 | -57.2 | 3.863 |
| app: standard | 2.09 | 2.437 | 3.427 | **1.253** | 0.716 | -62.633 | 2.847 |
| app: strong | 2.05 | 2.363 | **3.463** | 1.247 | 0.718 | -65.033 | **2.687** |

Listen: `bench/audio/<problem>/<method>.wav` (first voice).
