import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import interp1d
from matplotlib.ticker import MultipleLocator
from ac_parameters import *
from CG_calc import lemac, Aircraft


class LoadDiagram:
    def __init__(self, init_mass, init_cg, cmap='Set2', margin=2):
        self.acc_mass = init_mass
        self.acc_moment = [init_mass * init_cg, init_mass * init_cg]

        self.load_mass = {'OEW': [np.array([init_mass])]}
        self.load_cg = {'OEW': [np.array([init_cg])]}

        # Dummy variables
        self.cg_min = 100
        self.cg_max = 0

        self.cmap = cmap
        self.margin = margin

        self.cg_range = np.round(np.array([self.cg_min - self.margin, self.cg_max + self.margin]), 2)

    def calculate(self, payload, mass, arm, arm_conversion=True, loaded=False, fwd=True):
        acc_mass = self.acc_mass + np.hstack([0, np.cumsum(mass)])

        if arm_conversion:
            arm = lemac(arm)
        moment = mass * arm
        acc_moment = self.acc_moment[not fwd] + np.hstack([0, np.cumsum(moment)])
        cg = acc_moment / acc_mass

        self.cg_min = min(np.min(cg), self.cg_min)
        self.cg_max = max(np.max(cg), self.cg_max)

        if loaded:
            self.acc_mass = acc_mass[-1]
        if fwd:
            self.acc_moment[0] = acc_moment[-1]
        else:
            self.acc_moment[1] = acc_moment[-1]

        if payload in self.load_mass:
            self.load_mass[payload].append(acc_mass)
            self.load_cg[payload].append(cg)
        else:
            self.load_mass[payload] = [acc_mass]
            self.load_cg[payload] = [cg]

    def load_cargo(self, payload='Cargo', overload=False, max_cargo=plw - pax_n * pax_w):
        # fwd -> aft
        mass_fwd = cargo_mass.copy()
        mass_aft = np.flip(mass_fwd).copy()

        arm_fwd = cargo_arm
        arm_aft = np.flip(arm_fwd)

        max_cargo = int(max_cargo)
        if overload and max_cargo < np.sum(cargo_mass):
            for m in (mass_fwd, mass_aft):
                capacity = np.cumsum(m) - max_cargo
                m[capacity > 0] -= capacity[capacity > 0]
                m[m < 0] = np.zeros(len(m[m < 0]))  # Not fill the rest cargo holds
        self.calculate(payload, mass_fwd, arm_fwd)
        self.calculate(payload, mass_aft, arm_aft, loaded=True, fwd=False)

    def load_pilot(self, payload='Pilot', observer=False, loaded=True, fwd=True):
        crew = 2 if not observer else 3
        mass = np.ones(crew) * pilot_mass
        arm = np.ones(crew) * pilot_arm
        if observer:
            mass[-1] = obs_mass
            arm[-1] = obs_arm
        self.calculate(payload, mass, arm, loaded=loaded, fwd=fwd)

    def load_pax_w(self, pos, payload='Seats', n_seat=2, n_row=seat_row, w_pax=pax_w,
                   seat_counter=None):
        payload = f'{payload} ({pos})'

        # fwd -> aft
        arm = np.arange(n_row) * pitch + first_arm
        mass = np.ones(n_row) * n_seat * w_pax  # No order
        if seat_counter:
            for r, n in seat_counter.items():
                mass[r] = n * w_pax
        self.calculate(payload, mass, arm)
        self.calculate(payload, mass[::-1], arm[::-1], loaded=True, fwd=False)

    def load_fuel(self, payload='Fuel', fuel_arm_curve='linear',
                  fuel_limit=fw, load_limit=mtow, center_tank=False,
                  loaded=True, fwd=True):
        if center_tank:
            fuel_arm = interp1d(fuel_center, fuel_center_index)
        else:
            fuel_arm = interp1d(fuel_wing, fuel_wing_index, kind=fuel_arm_curve)

        ava_fuel = min(load_limit - self.acc_mass, fuel_limit)
        if ava_fuel <= 0:
            return

        fuel_load = np.linspace(0, ava_fuel, 10, retstep=True)
        # print(fuel_load)

        fuel_load, fuel_step = fuel_load[0][1:], fuel_load[1]
        fuel_load_index = fuel_arm(fuel_load) * -1

        arm = index_to_arm(fuel_load + self.acc_mass, fuel_load_index)

        fuel = np.ones(len(arm)) * fuel_step
        # arm = fuel_arm(ava_fuel / 2)  # Divide fuel into two tanks
        self.calculate(payload, fuel, arm, loaded=loaded, fwd=fwd)

    def load_seq(self, observer=False):
        self.load_pilot(observer=observer, loaded=False)
        self.load_pilot(observer=observer, fwd=False)
        self.load_pax_w('window')
        self.load_pax_w('aisle')
        self.load_pax_w('middle', n_seat=1, n_row=seat_row - 1)
        self.load_fuel('Fuel (wing)', fuel_arm_curve='quadratic', fuel_limit=fuel_wing_max, loaded=False)
        self.load_fuel('Fuel (wing)', fuel_arm_curve='quadratic', fuel_limit=fuel_wing_max, fwd=False)

        self.load_fuel('Fuel (center)', fuel_limit=fuel_center_max, center_tank=True, loaded=False)
        self.load_fuel('Fuel (center)', fuel_limit=fuel_center_max, center_tank=True, fwd=False)
        self.cg_range = np.round(np.array([self.cg_min - self.margin, self.cg_max + self.margin]), 2)

    def load_standard(self, observer=False, overload=False):
        self.load_cargo(overload=overload)
        self.load_seq(observer)

    def load_modified(self, observer=False, overload=False, oew_change=0):
        print(oew_change)
        self.load_cargo(overload=overload, max_cargo=(plw - oew_change) - pax_n * pax_w)  # Modified
        self.load_seq(observer)

    def plot(self, title='', overlay=False, save=None):
        # Limit of plot range
        x_lim = [((self.cg_min - self.margin) // 10 - 1) * 10,
                 ((self.cg_max + self.margin) // 10 + 1) * 10]
        y_lim = [oew // 2000 * 2000,
                 (mtow // 8000 + 1) * 8000]

        if self.cmap == 'gray':
            colors = ['lightgray'] * len(self.load_mass)
            alpha = 0.4
        else:
            color_map = plt.get_cmap(self.cmap)
            colors = color_map(np.arange(len(self.load_mass)))
            alpha = 1

            # MTOW line
            plt.axhline(y=mtow, linestyle='dashed', color='tomato')
            plt.text(x_lim[1] + 1, mtow - 150, 'MTOW')

            # MZFW line
            plt.axhline(y=self.load_mass['Fuel (wing)'][0][0], linestyle='dashed', color='lightsalmon', alpha=0.7)
            plt.text(x_lim[1] + 1, self.load_mass['Fuel (wing)'][0][0] - 150, 'MZFW')

        # Flip the plotting order (previous plotted line is on top)
        order = np.arange(1, len(self.load_mass) + 1)[::-1]

        ax = plt.subplot(111)
        for (l, m), cg, c, o in zip(self.load_mass.items(), self.load_cg.values(), colors, order):
            back = 0  # Check loading direction
            for lm, lcg in zip(m, cg):
                line_style = '-o' if back == 0 else '-^'
                label = '' if self.cmap == 'gray' else l  # Hide label if overlaid

                if label == 'OEW':
                    ax.plot(lcg, lm, 'o', color=c, label=label, zorder=o, alpha=alpha)
                else:
                    ax.plot(lcg, lm, line_style, color=c, label=label, zorder=o, alpha=alpha)

                back += 1

        if overlay:
            # Draw two dummy points to manually add two legend labels
            plt.plot(-1, 1, '-o', color='lightgray', label='Original design', alpha=alpha)
            plt.plot(-1, 1, '-^', color='lightgray', label='Original design', alpha=alpha)

        if self.cmap != 'gray':
            plt.xlim(x_lim)
            plt.ylim(y_lim)

            # Draw min / max CG lines
            plt.plot(np.ones(2) * (self.cg_min - self.margin), [y_lim[0], mtow], '-.k', label='Min/Max CG')
            plt.plot(np.ones(2) * (self.cg_max + self.margin), [y_lim[0], mtow], '-.k')

            box = ax.get_position()
            # Position legend at the bottom
            # ax.set_position([box.x0, box.y0 + box.height * 0.22,
            #                  box.width, box.height * 0.85])
            # plt.legend(loc='center', bbox_to_anchor=(0.5, -0.26), ncols=4)

            # Position the legend on the right side
            ax.set_position([box.x0 - box.width * 0.03, box.y0,
                             box.width * 0.8, box.height * 1.08])
            plt.legend(loc='lower left', bbox_to_anchor=(1.12, 0))

            # Minor tickers and grid
            ax.xaxis.set_minor_locator(MultipleLocator(2.5))
            ax.yaxis.set_minor_locator(MultipleLocator(500))
            plt.grid()

            # Axis label and title
            plt.xlabel(r'$x_{CG}$ [%MAC]')
            plt.ylabel('Mass [kg]')
            plt.title(title)

        if save:
            plt.savefig(f'plots/{save}.png', dpi=300)


if __name__ == '__main__':
    # fig = plt.figure(figsize=(7, 6))
    fig = plt.figure(figsize=(9, 5))  # Legend at right

    fokker = Aircraft()
    fokker_mod = Aircraft(mod=True)

    # Part I loading diagram
    ld_i = LoadDiagram(fokker.oew, fokker.cg_oew)
    ld_i.load_standard(True, True)
    print(ld_i.cg_range)
    # ld_i.plot(f'Loading diagram of Fokker 100, LEMAC @ {round(lemac_arm, 2)} m')
    # ld_i.plot(f'Loading diagram of Fokker 100, LEMAC @ {round(lemac_arm, 2)} m', save='loading_diagram_sep_I_r')

    # # Part II loading diagram
    # # Setting for overlaid plot
    # ld_o = LoadDiagram(fokker.oew, fokker.cg_oew, cmap='gray')
    # ld_o.load_standard(True, True)
    # ld_o.plot()
    #
    # ld_n = LoadDiagram(fokker_mod.oew, fokker_mod.cg_oew)
    # ld_n.load_modified(True, True, fokker_mod.mod[2])
    # # ld_n.plot('Loading diagram of Fokker 120 (modified design)', overlay=True)
    # ld_n.plot('Loading diagram of Fokker 120 (modified design)', overlay=True, save='loading_diagram_sep_II_r')

    plt.show()
