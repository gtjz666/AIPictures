# Human motion curve sources

The data used in this project was obtained from mocap.cs.cmu.edu.

These compact curve tables were extracted from CMU Graphics Lab captures:

- Jump: subject 16, motion 05, forward jump, 120 Hz; selected array indices 40–260.
- Attack: subject 14, motion 01, boxing, 120 Hz; selected array indices 120–230, with a short artistic impact hold at index 169.

Indices and the JSON `source_frame` values are zero-based. CMU AMC frame labels start at 1, so add 1 to these indices to locate the original labeled frame.

The JSON records the source URL, SHA-256 and the phase-to-source-frame map. Raw ASF/AMC files are not included. Directions and relative measures are projected into a side plane; the software retargets them to the reference character's own bone lengths. Global jump travel is excluded from PNG frames. These are deterministic controls, not a newly trained model or a guarantee of natural rendered results.

CMU's published terms permit inclusion in commercially sold products and ask for the attribution above. They prohibit directly reselling the capture data, including converted data. The CMU-derived tables carry those source terms, not the license for the project's Python code. Review the original terms at [CMU Graphics Lab Motion Capture Database](http://mocap.cs.cmu.edu/).

ASF/AMC transform interpretation follows [University of Wisconsin format documentation](https://research.cs.wisc.edu/graphics/Courses/cs-838-1999/Jeff/ASF-AMC.html). The parser and retargeting implementation were written for this project.
