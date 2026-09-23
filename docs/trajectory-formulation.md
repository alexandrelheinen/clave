# The trajectory formulation

How CLAVE plans the motion that takes a jaw onto an object the belt is
carrying. [requirements/arm-control.md](requirements/arm-control.md) states
what the controller has to do; this states the mathematics it does it with,
so a reader can check the algebra rather than trust the code.

## The problem

A limiter that walks a reference toward a goal under a speed and an
acceleration ceiling can arrive somewhere. It cannot pick anything up, for
one reason: it arrives when it arrives. A pick needs the arm to meet an
object **at a known instant, moving with it, having come straight down onto
it**, and none of those three is available from a trajectory whose duration
is an outcome.

So the duration becomes a parameter, and the whole formulation follows from
that one change.

Throughout, $\mathbf{p}_o(t)$ is the object's position, carried by the belt
at constant velocity $\mathbf{v}_o$, so

$$\mathbf{p}_o(t) = \mathbf{p}_o(t_0) + \mathbf{v}_o \,(t - t_0).$$

The belt drives one axis and leaves the others to physics, which is why
$\mathbf{v}_o = (v_b, 0, 0)$ with $v_b$ the belt speed.

## The segment

One arc is a **quintic Hermite polynomial per axis**, on normalized time
$s = (t - t_{\text{start}})/T \in [0, 1]$:

$$
p(s) = p_0 H_0(s) + T v_0 H_1(s) + T^2 a_0 H_2(s)
     + T^2 a_1 H_3(s) + T v_1 H_4(s) + p_1 H_5(s)
$$

with the basis

$$
\begin{aligned}
H_0(s) &= 1 - 10s^3 + 15s^4 - 6s^5, &
H_3(s) &= \tfrac{1}{2}s^3 - s^4 + \tfrac{1}{2}s^5, \\
H_1(s) &= s - 6s^3 + 8s^4 - 3s^5, &
H_4(s) &= -4s^3 + 7s^4 - 3s^5, \\
H_2(s) &= \tfrac{1}{2}s^2 - \tfrac{3}{2}s^3 + \tfrac{3}{2}s^4 - \tfrac{1}{2}s^5, &
H_5(s) &= 10s^3 - 15s^4 + 6s^5 .
\end{aligned}
$$

Velocity and acceleration follow by the chain rule, $\dot p = p'(s)/T$ and
$\ddot p = p''(s)/T^2$, and the basis is built so that

$$
p(0) = p_0,\quad \dot p(0) = v_0,\quad \ddot p(0) = a_0,\qquad
p(1) = p_1,\quad \dot p(1) = v_1,\quad \ddot p(1) = a_1 .
$$

**Why a quintic and not a B-spline.** Six boundary conditions per axis
against six coefficients means the polynomial is determined, not fitted:
there is no solver, no control net, and no residual. The requirement that
made the choice is control of acceleration at the waypoints, because two
arcs that only approach a common acceleration produce a step in it where
they meet, and a step in acceleration is a jerk the actuators answer with a
lurch. A Hermite form states $a_0$ and $a_1$ as coefficients; a B-spline
approaches them through control points.

## The sequence

A pick is five arcs. Each one's terminal state is the next one's initial
state, so the flange never stops between them.

| # | Arc | $\mathbf{p}$, $\mathbf{v}$, $\mathbf{a}$ at the end | Duration |
|---|---|---|---|
| 1 | Approach | $\mathbf{p}_o(t_0{+}T{+}\delta t) + \mathbf{z}$, $\;\mathbf{v}_o - V_a\hat{\mathbf{z}}$, $\;\mathbf{0}$ | $T$, solved |
| 2 | Descent | $\mathbf{p}_o(t_0{+}T{+}\delta t)$, $\;\mathbf{v}_o$, $\;\mathbf{0}$ | $\delta t$, derived |
| 3 | Grasp | held, moving with the belt | the dwell |
| 4 | Retreat | $\mathbf{p}_o + \mathbf{z}$, $\;\mathbf{v}_o + V_a\hat{\mathbf{z}}$, $\;\mathbf{0}$ | $\delta t$ |
| 5 | Deliver | the chute for the object's class, at rest | unconstrained |

where $\mathbf{z} = (0, 0, Z)$ is the clearance and $V_a$ the approach
speed. Arc 1 begins at the last drop point, at rest.

**The sequence mirrors itself about the pick.** Arcs 2 and 4 are one arc read
in opposite directions: the descent leaves the clearance at the approach speed
and reaches the object at the object's own velocity, and the retreat leaves the
object at that velocity and reaches the clearance at the object's velocity plus
the approach speed along the normal. They share $Z$, so they share the duration
$2Z/V_a$ as well. An arc that ends at rest destroys the mirror and, worse,
slides the flange backwards through the whole lift in the frame the object
lives in, because the object's frame carries the belt and the flange does not.

The arc that climbs from the clearance to the height the delivery crosses the
belt's side barrier at is **not** part of that mirror. It exists so the retreat
does not, and its shape is therefore allowed to depend on the barrier rather
than on the pick.

**Only the belt's axis is transported.** $\mathbf{v}_o = (v_b, 0, 0)$ above is
the model every prediction is made against, and an object's measured vertical
velocity is the belt settling it rather than transport. Feeding that component
back into the prediction is not a refinement of the model: over a two second
interception it asks for a grasp tens of millimetres below the object and, on
this line, below the belt.

## The interception time

Arc 1 has to end above where the object **will be** once arc 2 has also
finished, so its terminal condition contains its own duration:

$$
\mathbf{p}_{\text{approach}}(T) = \mathbf{p}_o(t_0) + \mathbf{v}_o (T + \delta t) + \mathbf{z}.
$$

$T$ is therefore a fixed point rather than something computed forward. Let
$\Sigma(T)$ be the arc built with that terminal condition and duration $T$,
and let

$$
\Phi(T) = \Big[\max_{s} \lVert \dot{\boldsymbol{\Sigma}}_T(s) \rVert \le v_{\max}\Big]
\wedge
\Big[\max_{s} \lVert \ddot{\boldsymbol{\Sigma}}_T(s) \rVert \le a_{\max}\Big]
$$

be the predicate that it is flyable. Both maxima fall as $T$ grows over the
range of interest, so $\Phi$ is monotone there and the soonest feasible
interception is

$$T^\star = \min \{\, T \in (0, T_{\max}] : \Phi(T) \,\}$$

found by **bisection**, not by an optimiser. This is suboptimal and it is
knowably suboptimal: a pick needs a duration it can count on, and a bound
that is monotone and cheap beats a minimum that is neither. When
$\Phi(T_{\max})$ is false the object is refused, because no interception
exists before it leaves the window.

The norms are over three axes, and the norm of a vector of polynomials is
not a polynomial, so the maxima are found by sampling the closed form
rather than by differentiating it.

## The descent duration

Not free, and this is the part most worth writing down.

In the frame moving with the belt the descent is purely vertical: from
height $Z$ with vertical speed $-V_a$ and no acceleration, to rest on the
object. Only two basis terms survive,

$$z(s) = Z\,H_0(s) - V_a\,\delta t\, H_1(s).$$

Position, velocity and acceleration all vanish at $s = 1$, so writing
$u = 1 - s$ the series about the end begins at $u^3$:

$$
z = -u^3\Big(3V_a\delta t\,u^2 - 7V_a\delta t\,u + 4V_a\delta t
    - 6Zu^2 + 15Zu - 10Z\Big),
$$

whose leading coefficient is

$$-2\,\big(2 V_a \delta t - 5 Z\big).$$

The flange therefore passes **below** the object it is descending onto
exactly when that coefficient turns negative, giving the condition

$$\boxed{\;\delta t \le \frac{5Z}{2V_a}\;}$$

Longer and the jaw closes through the object rather than around it. The
implementation uses

$$\delta t = \frac{2Z}{V_a},$$

four fifths of the limit, which leaves margin instead of sitting on a
boundary. Nothing is lost by that: acceleration is not the binding
constraint here, so stretching $\delta t$ toward the limit buys nothing,
and a shorter descent keeps the prediction horizon short, which is the
reason the clearance is small in the first place.

**This was wrong once and is worth recording as wrong.** The first
statement of the formulation said $2Z/V_a$ *was* the boundary, on the
strength of a numerical sweep that tried $1.0\times$ and $1.5\times$ that
value and saw a dip only at the second. Both observations are true and the
conclusion did not follow: the boundary is at $1.25\times$, and a sweep
that straddles it that widely cannot locate it. The test now brackets
$5Z/(2V_a)$ from both sides.

## Two corrections to the obvious terminal conditions

Both were measured rather than argued, and both are large.

**The pick does not end at rest.** A jaw arriving stopped has the object
sliding through it at $v_b$, which is the one thing a grasp cannot
tolerate. The terminal velocity of arc 2 is $\mathbf{v}_o$.

**Nor does the approach.** Arriving with no horizontal velocity forces arc
2 to cover the belt travel $v_b \delta t$ horizontally as well as
descending, and that catch-up, rather than the vertical braking, dominates
the acceleration. Measured at the shipped clearance, matching the object
took peak acceleration from $4.58$ to $0.94\ \mathrm{m/s^2}$, a factor of
about five, and the relative speed at the jaw from $0.314\ \mathrm{m/s}$ to
zero.

## Two closed forms worth having

For the rest-to-rest case, $v_0 = v_1 = a_0 = a_1 = 0$ over displacement
$D$, only $H_5$ survives and its derivatives factor:

$$
H_5'(s) = 30 s^2 (1-s)^2, \qquad H_5''(s) = 60 s (1-s)(1-2s),
$$

so the peaks are exact:

$$
\max \lvert \dot p \rvert = \frac{15}{8}\frac{D}{T} \ \text{at } s = \tfrac12,
\qquad
\max \lvert \ddot p \rvert = \frac{10}{\sqrt 3}\frac{D}{T^2}
\ \text{at } s = \tfrac12 \pm \tfrac{\sqrt3}{6}.
$$

The first gives a **feasibility condition that is not the obvious one**. As
$T$ grows the object recedes, so $D \to v_b T$ and the peak speed tends to
$\tfrac{15}{8} v_b$ rather than to zero. An interception exists only where

$$v_{\max} > \tfrac{15}{8}\, v_b \approx 1.875\, v_b,$$

so the arm has to outrun not the belt but nearly twice it. On the shipped
line that floor is $0.589\ \mathrm{m/s}$ against a ceiling of
$1.00\ \mathrm{m/s}$. A faster line, or a slower arm, crosses it long
before the two speeds meet.

## What the shipped line produces

From the park pose, across the reachable window, with $Z = 50\ \mathrm{mm}$,
$V_a = 0.25\ \mathrm{m/s}$ so $\delta t = 0.40\ \mathrm{s}$:

| Object at $x$ | $T$ | $T + \delta t$ | peak speed | peak acceleration |
|---|---|---|---|---|
| $-1.00$ m | 2.479 s | 2.879 s | 1.000 m/s | 1.457 m/s² |
| $-0.60$ m | 2.196 s | 2.596 s | 1.000 m/s | 1.574 m/s² |
| $-0.20$ m | 2.068 s | 2.468 s | 1.000 m/s | 1.556 m/s² |
| $+0.20$ m | 2.205 s | 2.605 s | 1.000 m/s | 1.367 m/s² |
| $+0.60$ m | 2.708 s | 3.108 s | 1.000 m/s | 1.095 m/s² |

**Speed binds and acceleration does not**, at every point tried: the peak
speed sits exactly on its ceiling while the acceleration sits near 1.5 of
an allowed 2.5. Raising $a_{\max}$ would buy nothing. Only a faster flange,
or a start closer to the belt, would shorten a visit.

## Motion reference and plant state

The arcs above are the motion layer. They live in the flat output: the
end-effector pose, velocity and acceleration the plan asks for. Once a visit
is committed, that state advances under a perfect-tracking model,

$$
\mathbf{x}_g(t + \mathrm{d}t) = \boldsymbol{\Sigma}(t + \mathrm{d}t),\qquad
T_{\mathrm{go}}(t + \mathrm{d}t) = T_{\mathrm{go}}(t) - \mathrm{d}t,
$$

so a re-aim or a re-solve begins at $\mathbf{x}_g(t)$, not at the measured
flange. The plant that trails, overshoots or collides is a control problem
for the servo; feeding it back into the plan turns a tracking error into a
new trajectory that rushes off the path the jaw was already following. The
requirement that states this is `AC-MOVE-68` in
[requirements/arm-control.md](requirements/arm-control.md).

## The target frame

The polynomials are defined in the **target frame**, not as free curves in
world. World commands are the composition of the model target pose with the
arc sample.

During intercept through retreat (and the climb that clears the belt), the
target is the object. Its model transport is belt-axis only,

$$
\mathbf{v}_T = (v_b, 0, 0)
$$

(or $(\max(0, v_x), 0, 0)$ when the estimate supplies $v_x$). Measured
lateral body velocity is not $\mathbf{v}_T$: it aims the target origin for a
finite horizon (`drift_horizon`) and does not become the velocity the jaw
matches on the hold or the retreat. In that frame the hold is rest (modulo
the closing rise) and the retreat is $+\hat{\mathbf{z}}$ over
$\delta t = 2Z / V_a$.

During delivery and release the target is the chute (or exit). The same
interception formulation applies with $\mathbf{v}_T = \mathbf{0}$: a
stationary intercept whose terminal velocity is rest. Pick and release
therefore differ only by which target owns the arcs and by whether that
target moves.

`AC-MOVE-69` through `AC-MOVE-72` in
[requirements/arm-control.md](requirements/arm-control.md) state the
requirements.

## What this does not settle

Whether the grasp holds. The formulation puts the jaw on the object at a
known instant with no relative slip, which is the precondition for a grasp
and not a grasp. Contact, grip force and whether a tumbling package stays
between the fingers are measured by the simulator once the segments are
wired through the task machine and the servo, and nothing here predicts
them.

Nor does it avoid obstacles. The arcs are unconstrained curves in task
space, kept inside the arm's annulus by projection and by nothing else. On
a belt carrying a single layer of objects with the gripper approaching from
directly above there is nothing to avoid, and that is an assumption about
the scene rather than a property of the method.
