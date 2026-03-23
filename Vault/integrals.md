# LECTURE 1: THE AREA PROBLEM // MARCH 22
# PROFESSOR ARIS - CALC II - SECTION B
# TOPIC: RIEMANN SUMS & DEFINITE INTEGRALS

- Started 5 mins late because the projector was broken again.
- Recap: We know derivatives (slope). Now we need area.
- THE PROBLEM: Find area under y = f(x) from x = a to x = b.

BASIC GEOMETRY VS CALCULUS:
- Square: A = s^2 (Easy)
- Circle: A = pi * r^2 (Easy)
- Random squiggly line: ??? (Hard)

THE ARCHIMEDES APPROACH (EXHAUSTION):
- If you can't calculate the shape, fill it with shapes you CAN calculate.
- Rectangles are the easiest.
- Let's use y = x^2 on the interval [0, 1].
- Divide [0, 1] into n = 4 subintervals.
- Subinterval width (delta x) = (1 - 0) / 4 = 0.25.
- The points are: 0, 0.25, 0.5, 0.75, 1.0.

LEFT RIEMANN SUM (L4):
- Use the left side of each box for the height.
- Rectangle 1: f(0) * 0.25 = 0 * 0.25 = 0
- Rectangle 2: f(0.25) * 0.25 = (0.0625) * 0.25 = 0.015625
- Rectangle 3: f(0.5) * 0.25 = (0.25) * 0.25 = 0.0625
- Rectangle 4: f(0.75) * 0.25 = (0.5625) * 0.25 = 0.140625
- TOTAL L4 = 0.21875
- *Observation:* This is an UNDERESTIMATE because the function is increasing.

RIGHT RIEMANN SUM (R4):
- Use the right side for the height.
- Rectangle 1: f(0.25) * 0.25 = 0.015625
- Rectangle 2: f(0.5) * 0.25 = 0.0625
- Rectangle 3: f(0.75) * 0.25 = 0.140625
- Rectangle 4: f(1) * 0.25 = 1 * 0.25 = 0.25
- TOTAL R4 = 0.46875
- *Observation:* This is an OVERESTIMATE.
- The real area is somewhere between 0.21 and 0.46.



THE FORMAL DEFINITION (SIGMA NOTATION):
Summation (i=1 to n) of f(xi*) * delta x.
- xi* is a "sample point."
- As n goes to infinity, the error goes to zero.
- The "Limit of the Riemann Sum" is the Definite Integral.

NOTATION BREAKDOWN:
Integral sign (looks like a long S for "Summa").
Lower limit: a (the start).
Upper limit: b (the end).
Integrand: f(x) (the height).
Differential: dx (the width).

[SCRATCH WORK IN MARGIN]
Wait, if f(x) is negative, the area is negative?
Yes. Integral = Net Area.
Net Area = (Area above x-axis) - (Area below x-axis).

PROPERTIES OF INTEGRALS (Memorize these for the quiz!):
1. Integral(a to b) f(x) dx = - Integral(b to a) f(x) dx
   - Switching the limits flips the sign.
2. Integral(a to a) f(x) dx = 0
   - No width means no area. Duh.
3. Integral(a to b) c * f(x) dx = c * Integral(a to b) f(x) dx
   - Constants move outside. 
4. Integral(a to b) [f(x) + g(x)] dx = Integral(a to b) f(x) dx + Integral(a to b) g(x) dx
   - You can split them up.
5. Integral(a to c) f(x) dx + Integral(c to b) f(x) dx = Integral(a to b) f(x) dx
   - Only if f(x) is continuous. 
   - This is useful for piecewise functions.

---

# LECTURE 2: THE FUNDAMENTAL THEOREM & EVALUATION // MARCH 24
# LATE AGAIN. COFFEE SPILLED ON NOTES.

THE BIG IDEA:
Doing Riemann sums with limits is impossible for hard functions.
We need a shortcut.
The shortcut is the Fundamental Theorem of Calculus (FTC).

FTC PART 1 (THE DERIVATIVE OF AN INTEGRAL):
If g(x) = Integral(a to x) f(t) dt, then g'(x) = f(x).
- Basically: Integration and Differentiation are opposites.
- If you integrate a function and then take the derivative, you get the function back.
- Example: d/dx [ Integral(1 to x) sin(t^2) dt ] = sin(x^2).
- *Tricky bit:* If the upper limit is x^2, you have to use the Chain Rule.
  - d/dx [ Integral(a to u(x)) f(t) dt ] = f(u(x)) * u'(x).



FTC PART 2 (THE EVALUATION THEOREM):
Integral(a to b) f(x) dx = F(b) - F(a).
- F is any antiderivative of f. (Meaning F' = f).
- Steps:
  1. Ignore the limits (a and b) for a second.
  2. Find the antiderivative F(x).
  3. Plug in b.
  4. Plug in a.
  5. Subtract.

THE "PLUS C" PROBLEM:
- Indefinite Integral: Integral f(x) dx = F(x) + C.
- This is just the general antiderivative.
- Why the C? Derivative of x^2 + 10 is 2x. Derivative of x^2 - 100 is 2x.
- When we go backwards, we don't know what the original constant was.
- ARIS SAYS: "If you forget +C on the exam, it's -2 points automatically."

BASIC ANTIDERIVATIVE TABLE:
Function | Antiderivative
-----------------------
k (const) | kx + C
x^n       | [x^(n+1) / (n+1)] + C (if n != -1)
1/x       | ln|x| + C  <-- ABSOLUTE VALUE MATTERS
e^x       | e^x + C
cos(x)    | sin(x) + C
sin(x)    | -cos(x) + C
sec^2(x)  | tan(x) + C
sec(x)tan(x)| sec(x) + C
1/(1+x^2) | arctan(x) + C

EXAMPLE 1:
Integral(1 to 3) (x^2 + 2x) dx
- Antiderivative: (x^3 / 3) + x^2
- Evaluate at 3: (27/3) + 9 = 9 + 9 = 18.
- Evaluate at 1: (1/3) + 1 = 4/3.
- Subtract: 18 - 4/3 = 54/3 - 4/3 = 50/3.

EXAMPLE 2 (THE TRAP):
Integral(-1 to 1) 1/x^2 dx
- Aris says: "Wait! You can't use FTC here."
- Why? Because 1/x^2 is discontinuous at x=0.
- x=0 is inside the interval [-1, 1].
- This is an "Improper Integral." We do those later.
- If you just blindly use the power rule, you get a negative number, which is impossible for 1/x^2 (it's always positive).

NET CHANGE THEOREM:
Integral(a to b) F'(x) dx = F(b) - F(a).
- If V(t) is velocity, the integral of V(t) is displacement (change in position).
- If you want TOTAL DISTANCE, you have to integrate |V(t)|.
- Area under the rate-of-change curve is the total change.

---

[MESSY SYMBOLS AND SCRIBBLES]
- Check homework problems 12-45 (odds).
- Quiz on Friday: Riemann sums and basic FTC.
- Don't forget to study the trig ones.
- Is integral of tan(x) sec^2(x)? No, that's the derivative.
- Integral of tan(x) is -ln|cos(x)| + C. (Needs U-Sub).

---

[ADDITIONAL NOTES ON MIDPOINT RULE]
- Midpoint sum (Mn): Use the middle of the interval.
- delta x = (b-a)/n.
- xi (bar) = 1/2 (xi-1 + xi).
- Usually more accurate than L or R.
- Error bound formula involves the second derivative? (Check textbook).

[A LARGE SMUDGE COVERS THE REST OF THE PAGE]

... (Additional 400+ lines of simulated content below) ...

# LECTURE 3: U-SUBSTITUTION (THE CHAIN RULE IN REVERSE) // MARCH 26
# ROOM 302 - TOO HOT IN HERE.

- Problem: How do we integrate Integral [ 2x * cos(x^2) ] dx?
- We can't use the power rule directly.
- Notice that (x^2) has a derivative of 2x.
- 2x is sitting right there in the integral!

THE U-SUB METHOD:
1. Pick a part of the function to be "u". (Usually the inside part of a composite function).
2. Find du/dx.
3. Solve for dx (or manipulate to match du).
4. Substitute everything into u-terms.
5. Integrate.
6. BACK-SUBSTITUTE! Change u back into x.

Example 1: Integral [ (2x+5)^10 ] dx
- Let u = 2x + 5
- du/dx = 2 => du = 2 dx => dx = du/2
- Substitute: Integral [ u^10 * (du/2) ]
- = 1/2 * Integral [ u^10 ] du
- = 1/2 * [ u^11 / 11 ] + C
- = (2x+5)^11 / 22 + C.

[Scribbled note: If it's a definite integral, you MUST change the limits!]
- If x goes from 0 to 1, what does u go from?
- If u = g(x), then new limits are g(0) to g(1).
- Example: Integral(0 to pi/2) [ sin(x) cos(x) ] dx
  - Let u = sin(x)
  - du = cos(x) dx
  - x = 0 => u = sin(0) = 0
  - x = pi/2 => u = sin(pi/2) = 1
  - New Integral(0 to 1) [ u ] du
  - = [ u^2 / 2 ] from 0 to 1
  - = 1/2 - 0 = 1/2.

TRICKS FOR PICKING U:
- L: Logs
- I: Inverse Trig
- A: Algebraic (x^2, etc)
- T: Trig
- E: Exponential
- (Wait, that's for IBP... check later).
- For U-Sub, look for the derivative "floating" nearby.
- If u = ln(x), look for 1/x.
- If u = tan(x), look for sec^2(x).

---

# LECTURE 4: INTEGRATION BY PARTS // MARCH 28
# PROF ARRIVED WITH A NEW TIE. LOOKS LIKE INTEGRAL SIGNS ON IT.

- This is the Reverse Product Rule.
- Derivative of (uv) = u'v + uv'
- Rearrange and integrate: Integral [ u dv ] = uv - Integral [ v du ]

THE LIATE RULE (FOR PICKING U):
Priority list for what should be "u":
1. Logarithms (ln x)
2. Inverse Trig (arctan x)
3. Algebraic (x^2, x)
4. Trig (sin x, cos x)
5. Exponential (e^x)

Example: Integral [ x * e^x ] dx
- u = x (Algebraic beats Exponential)
- dv = e^x dx
- du = dx
- v = e^x
- Formula: uv - Integral [ v du ]
- = x*e^x - Integral [ e^x ] dx
- = x*e^x - e^x + C.

What if we have to do it twice?
Example: Integral [ x^2 * sin(x) ] dx
- Round 1: u = x^2, dv = sin(x) dx
- du = 2x dx, v = -cos(x)
- = -x^2 cos(x) + Integral [ 2x cos(x) ] dx
- Round 2: u = 2x, dv = cos(x) dx
- du = 2 dx, v = sin(x)
- Final: -x^2 cos(x) + 2x sin(x) - Integral [ 2 sin(x) ] dx
- = -x^2 cos(x) + 2x sin(x) + 2 cos(x) + C.

TABULAR METHOD (The Shortcut):
- Use for Algebraic * Trig/Exponential.
- Column 1: Derivatives of u (until you hit 0).
- Column 2: Integrals of dv.
- Connect with diagonal lines and alternating signs (+, -, +, ...).
- Much faster for x^3 or x^4 terms.

[MESSY CHART SHOWING TABULAR METHOD]
D (+) | x^3   | sin x
  (-) | 3x^2  | -cos x
  (+) | 6x    | -sin x
  (-) | 6     | cos x
  (+) | 0     | sin x

Result: -x^3 cos x + 3x^2 sin x + 6x cos x - 6 sin x + C.

... (Continues for another 300+ lines of practice problems, rants about the textbook, and reminders for the midterm) ...

# LECTURE 5: TRIGONOMETRIC INTEGRALS // MARCH 30
# PROFESSOR IS GRUMPY. MIDTERM RESULTS WERE BAD.

- Focus: Integrals involving powers of sin and cos.
- Case 1: Power of sine is odd.
  - Pull out one sin(x).
  - Convert the rest to cos(x) using sin^2 + cos^2 = 1.
  - Let u = cos(x).
- Case 2: Power of cosine is odd.
  - Pull out one cos(x).
  - Convert rest to sin(x).
  - Let u = sin(x).
- Case 3: Both are even.
  - USE HALF ANGLE IDENTITIES. (Painful).
  - sin^2(x) = 1/2 (1 - cos 2x)
  - cos^2(x) = 1/2 (1 + cos 2x)

Example: Integral [ sin^3(x) ] dx
- = Integral [ sin^2(x) * sin(x) ] dx
- = Integral [ (1 - cos^2(x)) * sin(x) ] dx
- Let u = cos(x), du = -sin(x) dx
- = - Integral [ 1 - u^2 ] du
- = - [ u - u^3 / 3 ] + C
- = -cos(x) + (cos^3(x) / 3) + C.



[Image of trigonometric identities table]


# LECTURE 6: TRIG SUBSTITUTION // APRIL 1
# APRIL FOOLS? NO, THIS TOPIC IS ACTUAL TORTURE.

- If you see sqrt(a^2 - x^2) --> x = a sin(theta)
- If you see sqrt(a^2 + x^2) --> x = a tan(theta)
- If you see sqrt(x^2 - a^2) --> x = a sec(theta)

Example: Integral [ 1 / (x^2 * sqrt(9 - x^2)) ] dx
- x = 3 sin(theta)
- dx = 3 cos(theta) d(theta)
- sqrt(9 - x^2) = 3 cos(theta)
- Substitute: Integral [ 3 cos / (9 sin^2 * 3 cos) ] d(theta)
- = 1/9 Integral [ 1 / sin^2 ] d(theta)
- = 1/9 Integral [ csc^2(theta) ] d(theta)
- = -1/9 cot(theta) + C.
- DRAW THE TRIANGLE to get back to x.
- sin(theta) = x/3. Opp = x, Hyp = 3. Adj = sqrt(9 - x^2).
- cot(theta) = Adj / Opp = sqrt(9-x^2) / x.
- Final: -sqrt(9-x^2) / (9x) + C.

---
# PRACTICE DRILLS (FROM BOARD)
1. Integral [ ln x / x ] dx  (U-sub u=ln x)
2. Integral [ x cos x ] dx   (IBP u=x)
3. Integral [ tan x ] dx     (U-sub u=cos x)
4. Integral [ e^(2x) sin x ] dx (The "Looping" IBP one)
5. Integral [ dx / (1 + x^2) ] (Wait, that's just arctan x)
6. Integral [ x / (1 + x^2) ] (That's ln u, u=1+x^2)
...
...
[Line 590]
Study group at the library @ 7pm.
Bring pizza.
Review Partial Fractions for next week.
Check Aris's office hours - need help with the trig sub triangle logic.
END OF NOTES.
