# Learn & Fix: An Interactive Topology Feedback System for Blender

Learn & Fix is an open-source Blender add-on that helps novice 3D modellers identify, navigate, and understand topological errors. It functions as both a real-time diagnostic tool and an educational scaffolding system, utilising Blender's `bmesh` API and spatial Bounding Volume Hierarchy (BVH) trees to detect geometric irregularities while providing context-sensitive theoretical documentation and remediation guidance. This software artefact was developed as part of the research paper:

Bridging the Learning Gap in 3D Modelling: Design of an Interactive Topology Feedback System for Blender

---

Overview

Unlike standard mesh validation toolkits that output raw vertex indices, Learn & Fix implements an active interventional learning workflow. It continuously monitors viewport editing operations and delivers event-driven feedback, complemented by an integrated "Explain & Fix" module that grounds error explanations in 3D computer graphics theory (e.g., how N-gons disrupt subdivision surface algorithms).

# Core Functionalities
1. Automated Error Detection: Real-time and event-driven scanning across four fundamental diagnostic categories.
2. Smooth Camera Navigation: Automated 3D Viewport camera framing utilising Spherical Linear Interpolation (`slerp`) and Linear Interpolation (`lerp`)  to isolate and highlight detected geometric defects without disorienting the user.
3. Contextual Pedagogical Guidance: An integrated "Explain & Fix" modal dialogue offering visual diagrams, theoretical context, and user-executed step-by-step repair strategies.
4. Tailored Workflow Presets: Industry-aligned diagnostic profiles (3D Printing, Game Assets, Animation, Expert) that automatically filter irrelevant rules.
5. Onboarding Visual Assistance: A dedicated Viewport Initiator Button embedded in the top header ribbon to resolve initial Sidebar (N-panel) discoverability friction.

---

 Technical Specifications & Diagnostic Checks

# Supported Diagnostic Checks
The rule-based detection engine executes four core algorithms structured as an instructional scaffold:
* Unapplied Transforms (Object-Level Preparation): Evaluates object matrices to detect unapplied Scale (1.0) or Rotation (0) that cause non-uniform modifier behaviour.
* Zero-Area Faces (Basic Structural Integrity): Iterates over BMesh faces to identify degenerate surfaces below numerical precision thresholds (Area < 1e-8^2).
* Self-Intersecting Geometry (Basic Structural Integrity): Constructs spatial Bounding Volume Hierarchy (BVH) trees to evaluate face-to-face mesh intersections using `bmesh.ops.intersect_faces`.
* N-Gons (Topology Optimisation): Flags polygonal faces containing more than four vertices (X > 4) to prevent shading artefacts and deformation issues.

# Technical Architecture
* Environment: Python 3.10+
* Core APIs: Blender Python API (`bpy`, `bmesh`, `mathutils`)
* Design Pattern: Modular architecture separating core diagnostic algorithms (`bmesh` loops, BVH spatial trees) from UI presentation (`bpy.types.Panel`, modal dialogue operators).
* Event System: Employs `bpy.app.handlers` for event-driven dependency graph monitoring, supplemented by an optional periodic Auto-Check operator (every 10 viewport actions).

---

 Installation

1. Download the latest release package (`.zip`).
2. Launch Blender (Version 3.0 or newer).
3. Navigate to Edit > Preferences > Add-ons.
4. Click Install... and select the downloaded `.zip` file.
5. Enable the checkbox next to "3D View: Learn & Fix".
6. Open the 3D Viewport Sidebar by pressing `N` and locate the "Learn & Fix" tab (or click the flashing Viewport Initiator Button in the top header).

---

Usage Guide

1. Workflow Selection
Select a Workflow Mode from the main panel (3D Printing, Game Assets, Animation, Expert). The add-on dynamically filters active diagnostic checks to match your target production pipeline.

2. Mesh Analysis
Click Check Mesh to execute the diagnostic suite. The add-on displays categorised error logs alongside a health summary.

3. Error Navigation & Remediation
Next / Previous: Cycles through the list of identified errors.
Show: Smoothly interpolates (using `slerp` & `lerp`) the camera to frame the specific defect in the 3D Viewport.
Explain & Fix: Opens the modal dialogue containing visual diagrams, theoretical explanations, and manual repair instructions.
