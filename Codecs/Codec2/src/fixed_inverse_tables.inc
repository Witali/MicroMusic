/*
Copyright (c) 2003-2010, Mark Borgerding

All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
this list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.
    * Neither the author nor the names of any contributors may be used to
endorse or promote products derived from this software without specific prior
written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/
/* Generated from the pinned original KISS binary32 angles.
 * Quarter sine for a 512-point real FFT; nearest integer.
 */
/* Q6: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 6
static const uint8_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 9,
    9, 10, 11, 12, 12, 13, 14, 15, 16, 16, 17, 18,
    19, 19, 20, 21, 22, 22, 23, 24, 24, 25, 26, 27,
    27, 28, 29, 29, 30, 31, 32, 32, 33, 34, 34, 35,
    36, 36, 37, 37, 38, 39, 39, 40, 41, 41, 42, 42,
    43, 44, 44, 45, 45, 46, 46, 47, 47, 48, 48, 49,
    49, 50, 50, 51, 51, 52, 52, 53, 53, 54, 54, 54,
    55, 55, 56, 56, 56, 57, 57, 58, 58, 58, 59, 59,
    59, 59, 60, 60, 60, 61, 61, 61, 61, 61, 62, 62,
    62, 62, 62, 63, 63, 63, 63, 63, 63, 63, 64, 64,
    64, 64, 64, 64, 64, 64, 64, 64, 64,
};
#endif
/* Q7: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 7
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 2, 3, 5, 6, 8, 9, 11, 13, 14, 16, 17,
    19, 20, 22, 23, 25, 27, 28, 30, 31, 33, 34, 36,
    37, 39, 40, 42, 43, 45, 46, 48, 49, 50, 52, 53,
    55, 56, 58, 59, 60, 62, 63, 64, 66, 67, 68, 70,
    71, 72, 74, 75, 76, 78, 79, 80, 81, 82, 84, 85,
    86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98,
    99, 100, 101, 102, 103, 104, 105, 106, 106, 107, 108, 109,
    110, 111, 111, 112, 113, 114, 114, 115, 116, 116, 117, 118,
    118, 119, 119, 120, 121, 121, 122, 122, 122, 123, 123, 124,
    124, 125, 125, 125, 126, 126, 126, 126, 127, 127, 127, 127,
    127, 128, 128, 128, 128, 128, 128, 128, 128,
};
#endif
/* Q8: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 8
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 3, 6, 9, 13, 16, 19, 22, 25, 28, 31, 34,
    38, 41, 44, 47, 50, 53, 56, 59, 62, 65, 68, 71,
    74, 77, 80, 83, 86, 89, 92, 95, 98, 101, 104, 107,
    109, 112, 115, 118, 121, 123, 126, 129, 132, 134, 137, 140,
    142, 145, 147, 150, 152, 155, 157, 160, 162, 165, 167, 170,
    172, 174, 177, 179, 181, 183, 185, 188, 190, 192, 194, 196,
    198, 200, 202, 204, 206, 207, 209, 211, 213, 215, 216, 218,
    220, 221, 223, 224, 226, 227, 229, 230, 231, 233, 234, 235,
    237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248,
    248, 249, 250, 250, 251, 252, 252, 253, 253, 254, 254, 254,
    255, 255, 255, 256, 256, 256, 256, 256, 256,
};
#endif
/* Q9: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 9
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 6, 13, 19, 25, 31, 38, 44, 50, 56, 63, 69,
    75, 81, 88, 94, 100, 106, 112, 118, 124, 130, 137, 143,
    149, 155, 161, 167, 172, 178, 184, 190, 196, 202, 207, 213,
    219, 225, 230, 236, 241, 247, 252, 258, 263, 269, 274, 279,
    284, 290, 295, 300, 305, 310, 315, 320, 325, 330, 334, 339,
    344, 348, 353, 358, 362, 366, 371, 375, 379, 384, 388, 392,
    396, 400, 404, 407, 411, 415, 419, 422, 426, 429, 433, 436,
    439, 442, 445, 449, 452, 454, 457, 460, 463, 465, 468, 471,
    473, 475, 478, 480, 482, 484, 486, 488, 490, 492, 493, 495,
    497, 498, 500, 501, 502, 503, 504, 505, 506, 507, 508, 509,
    510, 510, 511, 511, 511, 512, 512, 512, 512,
};
#endif
/* Q10: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 10
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 13, 25, 38, 50, 63, 75, 88, 100, 113, 125, 138,
    150, 163, 175, 187, 200, 212, 224, 237, 249, 261, 273, 285,
    297, 309, 321, 333, 345, 357, 369, 380, 392, 403, 415, 426,
    438, 449, 460, 472, 483, 494, 505, 516, 526, 537, 548, 558,
    569, 579, 590, 600, 610, 620, 630, 640, 650, 659, 669, 678,
    688, 697, 706, 715, 724, 733, 742, 750, 759, 767, 775, 784,
    792, 799, 807, 815, 822, 830, 837, 844, 851, 858, 865, 872,
    878, 885, 891, 897, 903, 909, 915, 920, 926, 931, 936, 941,
    946, 951, 955, 960, 964, 968, 972, 976, 980, 983, 987, 990,
    993, 996, 999, 1002, 1004, 1007, 1009, 1011, 1013, 1015, 1016, 1018,
    1019, 1020, 1021, 1022, 1023, 1023, 1024, 1024, 1024,
};
#endif
/* Q11: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 11
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 25, 50, 75, 100, 126, 151, 176, 201, 226, 251, 276,
    301, 325, 350, 375, 400, 424, 449, 473, 498, 522, 546, 570,
    595, 619, 642, 666, 690, 714, 737, 760, 784, 807, 830, 853,
    876, 898, 921, 943, 965, 988, 1009, 1031, 1053, 1074, 1096, 1117,
    1138, 1159, 1179, 1200, 1220, 1240, 1260, 1280, 1299, 1319, 1338, 1357,
    1375, 1394, 1412, 1430, 1448, 1466, 1483, 1500, 1517, 1534, 1551, 1567,
    1583, 1599, 1615, 1630, 1645, 1660, 1674, 1689, 1703, 1717, 1730, 1744,
    1757, 1769, 1782, 1794, 1806, 1818, 1829, 1840, 1851, 1862, 1872, 1882,
    1892, 1902, 1911, 1920, 1928, 1937, 1945, 1952, 1960, 1967, 1974, 1980,
    1987, 1993, 1998, 2004, 2009, 2013, 2018, 2022, 2026, 2029, 2033, 2036,
    2038, 2040, 2042, 2044, 2046, 2047, 2047, 2048, 2048,
};
#endif
/* Q12: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 12
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 50, 101, 151, 201, 251, 301, 351, 401, 451, 501, 551,
    601, 651, 700, 750, 799, 848, 897, 946, 995, 1044, 1092, 1141,
    1189, 1237, 1285, 1332, 1380, 1427, 1474, 1521, 1567, 1614, 1660, 1706,
    1751, 1797, 1842, 1886, 1931, 1975, 2019, 2062, 2106, 2149, 2191, 2234,
    2276, 2317, 2359, 2399, 2440, 2480, 2520, 2559, 2598, 2637, 2675, 2713,
    2751, 2788, 2824, 2861, 2896, 2932, 2967, 3001, 3035, 3068, 3102, 3134,
    3166, 3198, 3229, 3260, 3290, 3320, 3349, 3378, 3406, 3433, 3461, 3487,
    3513, 3539, 3564, 3588, 3612, 3636, 3659, 3681, 3703, 3724, 3745, 3765,
    3784, 3803, 3822, 3839, 3857, 3873, 3889, 3905, 3920, 3934, 3948, 3961,
    3973, 3985, 3996, 4007, 4017, 4027, 4036, 4044, 4052, 4059, 4065, 4071,
    4076, 4081, 4085, 4088, 4091, 4093, 4095, 4096, 4096,
};
#endif
/* Q13: shared quarter wave differs from original super twiddles by at most 0 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 13
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 101, 201, 302, 402, 502, 603, 703, 803, 903, 1003, 1102,
    1202, 1301, 1401, 1499, 1598, 1697, 1795, 1893, 1990, 2088, 2185, 2282,
    2378, 2474, 2570, 2665, 2760, 2854, 2948, 3042, 3135, 3228, 3320, 3411,
    3503, 3593, 3683, 3773, 3862, 3950, 4038, 4125, 4212, 4297, 4383, 4467,
    4551, 4634, 4717, 4799, 4880, 4960, 5040, 5119, 5197, 5274, 5351, 5427,
    5501, 5575, 5649, 5721, 5793, 5863, 5933, 6002, 6070, 6137, 6203, 6268,
    6333, 6396, 6458, 6519, 6580, 6639, 6698, 6755, 6811, 6867, 6921, 6974,
    7027, 7078, 7128, 7177, 7225, 7272, 7317, 7362, 7405, 7448, 7489, 7529,
    7568, 7606, 7643, 7679, 7713, 7746, 7779, 7809, 7839, 7868, 7895, 7921,
    7946, 7970, 7993, 8014, 8035, 8054, 8071, 8088, 8103, 8117, 8130, 8142,
    8153, 8162, 8170, 8177, 8182, 8186, 8190, 8191, 8192,
};
#endif
/* Q14: shared quarter wave differs from original super twiddles by at most 1 unit. */
#if CODEC2_FIXED_TWIDDLE_Q == 14
static const uint16_t fixed_sine[129] CODEC2_TABLE_STORAGE = {
    0, 201, 402, 603, 804, 1005, 1205, 1406, 1606, 1806, 2006, 2205,
    2404, 2603, 2801, 2999, 3196, 3393, 3590, 3786, 3981, 4176, 4370, 4563,
    4756, 4948, 5139, 5330, 5520, 5708, 5897, 6084, 6270, 6455, 6639, 6823,
    7005, 7186, 7366, 7545, 7723, 7900, 8076, 8250, 8423, 8595, 8765, 8935,
    9102, 9269, 9434, 9598, 9760, 9921, 10080, 10238, 10394, 10549, 10702, 10853,
    11003, 11151, 11297, 11442, 11585, 11727, 11866, 12004, 12140, 12274, 12406, 12537,
    12665, 12792, 12916, 13039, 13160, 13279, 13395, 13510, 13623, 13733, 13842, 13949,
    14053, 14155, 14256, 14354, 14449, 14543, 14635, 14724, 14811, 14896, 14978, 15059,
    15137, 15213, 15286, 15357, 15426, 15493, 15557, 15619, 15679, 15736, 15791, 15843,
    15893, 15941, 15986, 16029, 16069, 16107, 16143, 16176, 16207, 16235, 16261, 16284,
    16305, 16324, 16340, 16353, 16364, 16373, 16379, 16383, 16384,
};
#endif
