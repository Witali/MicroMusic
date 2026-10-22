CXX ?= g++
CXXFLAGS ?= -std=c++11 -O2 -Wall -Wextra -Werror

.PHONY: test synthetic clean

test: build/decode_host build/test_mul16 build/test_buffer
	./build/test_mul16
	python3 tests/test_regression.py

synthetic:
	python3 tools/synthetic_demo.py
	python3 tools/make_header.py examples/LPX3_PROGMEM/synthetic_voice.l3av examples/LPX3_PROGMEM/voice_data.h

build/decode_host: src/Lpx3AvrCore.cpp src/Lpx3AvrCore.h tests/decode_host.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) src/Lpx3AvrCore.cpp tests/decode_host.cpp -o $@

build/test_buffer: src/Lpx3AvrCore.cpp src/Lpx3AvrCore.h tests/test_buffer.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) src/Lpx3AvrCore.cpp tests/test_buffer.cpp -o $@

build/test_mul16: tests/test_mul16.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) tests/test_mul16.cpp -o $@

clean:
	rm -rf build
