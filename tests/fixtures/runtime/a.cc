extern "C" int forge_b_value();
extern "C" int forge_a_value() { return forge_b_value() + 1; }
