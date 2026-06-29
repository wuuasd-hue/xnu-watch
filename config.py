"""
config.py — XNU/Apple Security Watch icin tarama hedefleri ve ayarlar.

Her hedef bir "lens_key" tasir (prompts.py -> TARGET_LENSES ile eslesir):
xnu | dyld | gatekeeper | webkit_swift
"""

WATCH_TARGETS = [
    {
        "repo": "apple-oss-distributions/xnu",
        "paths": [],
        "lens_key": "xnu",
        "description": "XNU kernel kaynak kodu (Mach + BSD + IOKit-adjacent)",
    },
    {
        "repo": "apple-oss-distributions/dyld",
        "paths": [],
        "lens_key": "dyld",
        "description": "Dinamik loader/linker - Mach-O parsing, code-signing dogrulama",
    },
    {
        "repo": "apple-oss-distributions/Security",
        "paths": [],
        "lens_key": "gatekeeper",
        "description": "Security framework - quarantine/trust policy mantigi (Gatekeeper'a yakin)",
    },
    {
        "repo": "WebKit/WebKit",
        "paths": ["Source/JavaScriptCore", "Source/WebCore/loader"],
        "lens_key": "webkit_swift",
        "description": "JSC ve WebCore loader - en sik exploit edilen Apple yuzeyi",
    },
    {
        "repo": "swiftlang/swift",
        "paths": ["stdlib/public/runtime"],
        "lens_key": "webkit_swift",
        "description": "Swift runtime - bellek guvenligi/tip sistemi hassas alanlari",
    },
]

# NOT: apple-oss-distributions organizasyonu, opensource.apple.com'un GitHub
# mirror'udur (XNU, dyld, Security, Libc vb. buradan resmi olarak yayinlanir).

# Bir taramada en fazla kac "supheli aday" derin analize gonderilsin
# (ucretsiz API kotalarini asmamak icin sinir)
MAX_CANDIDATES_PER_RUN = 4  # 6 model x 3 katman x N aday = cok call, dusuk tut

# Cross-check icin kac modelden en az kac tanesi "supheli" demeli
CONSENSUS_THRESHOLD = 4  # 6 modelden en az 4'u onaylamali

# Starvation modu: son kac saattir REPORTABLE bulgu yoksa idle moda gecilsin
STARVATION_HOURS = 10

