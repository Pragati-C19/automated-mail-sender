#!/bin/bash

OUTPUT="data/accessibility-report.txt"

# Clear previous report
> "$OUTPUT"

sites=(

"https://prpedge.com"

"https://svanim.com"

"https://svobodha.com"

"https://rbsa.in"

"https://askim.co.in"

"https://fourdimensions.in"

"https://fortunaam.in"

"https://thinqwise.com"

"https://sowiloim.com"

"https://sohumam.com"

"https://gaja.capital"

"https://lccapital.in"

"https://cbadvisor.in"

"https://lighthouseamc.com"

"https://cosmea.in"

)

for site in "${sites[@]}"; do
    echo "==================================================" >> "$OUTPUT"
    echo "Website: $site" >> "$OUTPUT"
    echo "==================================================" >> "$OUTPUT"

    npx @axe-core/cli "$site" >> "$OUTPUT" 2>&1

    echo "" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
done

echo "Done! Report saved to $OUTPUT"

# command to run the script: bash scan.sh or sh scan.sh