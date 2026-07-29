// Fullscreen post-process vertex shader.
//
// Derived from panda3d-simplepbr 0.13.1 (post.vert), Copyright (c) 2019,
// Mitchell Stokes, used under the BSD 3-Clause License. See
// THIRD_PARTY_NOTICES.md at the repository root.

#version 330

uniform mat4 p3d_ModelViewProjectionMatrix;

in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;

out vec2 v_texcoord;

void main() {
    v_texcoord = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
