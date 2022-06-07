from typing import Callable, Union, Any
from warnings import warn
from enum import Enum

import biorbd_casadi as biorbd
from casadi import vertcat, MX

from .penalty import PenaltyOption
from .path_conditions import Bounds
from .objective_functions import ObjectiveFunction
from ..limits.penalty import PenaltyFunctionAbstract, PenaltyNodeList
from ..misc.enums import Node, InterpolationType, ConstraintType
from ..misc.options import UniquePerPhaseOptionList


class MultinodePenalty(PenaltyOption):
    """
    A placeholder for a multi node penalties

    Attributes
    ----------
    min_bound: list
        The minimal bound of the multi node penalties
    max_bound: list
        The maximal bound of the multi node penalties
    bounds: Bounds
        The bounds (will be filled with min_bound/max_bound)
    weight: float
        The weight of the cost function
    quadratic: bool
        If the objective function is quadratic
    phase_first_idx: int
        The first index of the phase of concern
    phase_second_idx: int
        The second index of the phase of concern
    first_node: Node
        The kind of the first node
    second_node: Node
        The kind of the second node
    dt: float
        The delta time
    node_idx: int
        The index of the node in nlp pre
    multinode_penalty: Union[Callable, Any]
        The nature of the cost function is the multi node penalty
    constraint_type: ConstraintType
        If the penalty is from the user or from bioptim (implicit or internal)
    """

    def __init__(
        self,
        phase_first_idx: int,
        phase_second_idx: int,
        first_node: Union[Node, int],
        second_node: Union[Node, int],
        multinode_penalty: Union[Callable, Any] = None,
        custom_function: Callable = None,
        min_bound: float = 0,
        max_bound: float = 0,
        weight: float = 0,
        **params: Any,
    ):
        """
        Parameters
        ----------
        phase_first_idx: int
            The first index of the phase of concern
        params:
            Generic parameters for options
        """

        force_multinode = False
        if "force_multinode" in params:
            # This is a hack to circumvent the apparatus that moves the functions to a custom function
            # It is necessary for PhaseTransition
            force_multinode = True
            del params["force_multinode"]

        if not isinstance(multinode_penalty, MultinodePenaltyFcn) and not force_multinode:
            custom_function = multinode_penalty
            multinode_penalty = MultinodePenaltyFcn.CUSTOM
        super(PenaltyOption, self).__init__(penalty=multinode_penalty, custom_function=custom_function, **params)

        if first_node not in (Node.START, Node.MID, Node.PENULTIMATE, Node.END):
            if not isinstance(first_node, int):
                raise NotImplementedError(
                    "Multi Node Penalty only works with Node.START, Node.MID, Node.PENULTIMATE, Node.END or a int."
                )
        if second_node not in (Node.START, Node.MID, Node.PENULTIMATE, Node.END):
            if not isinstance(second_node, int):
                raise NotImplementedError(
                    "Multi Node Penalty only works with Node.START, Node.MID, Node.PENULTIMATE, Node.END or a int."
                )
        self.min_bound = min_bound
        self.max_bound = max_bound
        self.bounds = Bounds(interpolation=InterpolationType.CONSTANT)

        self.multinode_penalty = True
        self.weight = weight
        self.quadratic = True
        self.phase_first_idx = phase_first_idx
        self.phase_second_idx = phase_second_idx
        self.phase_pre_idx = phase_first_idx
        self.phase_post_idx = phase_second_idx
        self.first_node = first_node
        self.second_node = second_node
        self.node = self.first_node, self.second_node
        self.dt = 1
        self.node_idx = [0]
        self.constraint_type = ConstraintType.INTERNAL

    def _add_penalty_to_pool(self, all_pn: Union[PenaltyNodeList, list, tuple]):
        ocp = all_pn[0].ocp
        nlp = all_pn[0].nlp
        if self.weight == 0:
            pool = nlp.g_internal if nlp else ocp.g_internal
        else:
            pool = nlp.J_internal if nlp else ocp.J_internal
        pool[self.list_index] = self

    def clear_penalty(self, ocp, nlp):
        if self.weight == 0:
            g_to_add_to = nlp.g_internal if nlp else ocp.g_internal
        else:
            g_to_add_to = nlp.J_internal if nlp else ocp.J_internal

        if self.list_index < 0:
            for i, j in enumerate(g_to_add_to):
                if not j:
                    self.list_index = i
                    return
            else:
                g_to_add_to.append([])
                self.list_index = len(g_to_add_to) - 1
        else:
            while self.list_index >= len(g_to_add_to):
                g_to_add_to.append([])
            g_to_add_to[self.list_index] = []


class MultinodePenaltyList(UniquePerPhaseOptionList):
    """
    A list of Multi Node Penalty

    Methods
    -------
    add(self, transition: Union[Callable, PhaseTransitionFcn], phase: int = -1, **extra_arguments)
        Add a new MultinodePenalty to the list
    print(self)
        Print the MultinodePenaltyList to the console
    prepare_multinode_penalty(self, ocp) -> list
        Configure all the multinode_penalty and put them in a list
    """

    def add(self, multinode_penalty: Any, **extra_arguments: Any):
        """
        Add a new MultinodePenalty to the list

        Parameters
        ----------
        multinode_penalty: Union[Callable, MultinodePenaltyFcn]
            The chosen phase transition
        extra_arguments: dict
            Any parameters to pass to Penalty
        """

        if not isinstance(multinode_penalty, MultinodePenaltyFcn):
            extra_arguments["custom_function"] = multinode_penalty
            multinode_penalty = MultinodePenaltyFcn.CUSTOM
        super(MultinodePenaltyList, self)._add(
            option_type=MultinodePenalty, multinode_penalty=multinode_penalty, phase=-1, **extra_arguments
        )

    def print(self):
        """
        Print the MultinodePenaltyList to the console
        """
        raise NotImplementedError("Printing of MultinodePenaltyList is not ready yet")

    def prepare_multinode_penalties(self, ocp) -> list:
        """
        Configure all the phase transitions and put them in a list

        Parameters
        ----------
        ocp: OptimalControlProgram
            A reference to the ocp

        Returns
        -------
        The list of all the multi_node penalties prepared
        """
        full_phase_multinode_penalty = []
        existing_phases = []
        for mnc in self:

            idx_phase = mnc.phase_first_idx
            if mnc.phase_first_idx >= ocp.n_phases or mnc.phase_second_idx >= ocp.n_phases:
                raise RuntimeError("Phase index of the multinode_penalty is higher than the number of phases")
            if mnc.phase_first_idx < 0 or mnc.phase_second_idx < 0:
                raise RuntimeError("Phase index of the multinode_penalty need to be positive")
            existing_phases.append(idx_phase)

            if mnc.weight:
                mnc.base = ObjectiveFunction.MayerFunction

            full_phase_multinode_penalty.append(mnc)

        return full_phase_multinode_penalty


class MultinodePenaltyFunctions(PenaltyFunctionAbstract):
    """
    Internal implementation of the phase transitions
    """

    class Functions:
        """
        Implementation of all the Multi Node Penalty
        """

        @staticmethod
        def equality(multinode_penalty, all_pn):
            """
            The most common continuity function, that is state before equals state after

            Parameters
            ----------
            multinode_penalty : MultinodePenalty
                A reference to the phase transition
            all_pn: PenaltyNodeList
                    The penalty node elements

            Returns
            -------
            The difference between the state after and before
            """

            nlp_pre, nlp_post = all_pn[0].nlp, all_pn[1].nlp
            states_pre = multinode_penalty.states_mapping.to_second.map(nlp_pre.states.cx_end)
            states_post = multinode_penalty.states_mapping.to_first.map(nlp_post.states.cx)

            if states_pre.shape != states_post.shape:
                raise RuntimeError(
                    f"Continuity can't be established since the number of x to be matched is {states_pre.shape} in the "
                    f"pre-transition phase and {states_post.shape} post-transition phase. Please use a custom "
                    f"transition or supply states_mapping"
                )

            return states_pre - states_post

        @staticmethod
        def com_equality(multinode_penalty, all_pn):
            """
            The centers of mass are equals for the specified phases and the specified nodes

            Parameters
            ----------
            multinode_penalty : MultinodePenalty
                A reference to the phase transition
            all_pn: PenaltyNodeList
                    The penalty node elements

            Returns
            -------
            The difference between the state after and before
            """

            nlp_pre, nlp_post = all_pn[0].nlp, all_pn[1].nlp
            states_pre = multinode_penalty.states_mapping.to_second.map(nlp_pre.states.cx_end)
            states_post = multinode_penalty.states_mapping.to_first.map(nlp_post.states.cx)

            states_post_sym_list = [MX.sym(f"{key}", *nlp_post.states[key].mx.shape) for key in nlp_post.states.keys()]
            states_post_sym = vertcat(*states_post_sym_list)

            if states_pre.shape != states_post.shape:
                raise RuntimeError(
                    f"Continuity can't be established since the number of x to be matched is {states_pre.shape} in the "
                    f"pre-transition phase and {states_post.shape} post-transition phase. Please use a custom "
                    f"transition or supply states_mapping"
                )

            pre_com = nlp_pre.model.CoM(states_pre[nlp_pre.states["q"].index, :]).to_mx()
            post_com = nlp_post.model.CoM(states_post_sym_list[0]).to_mx()

            pre_states_cx = nlp_pre.states.cx
            post_states_cx = nlp_post.states.cx

            return biorbd.to_casadi_func(
                "com_equality",
                pre_com - post_com,
                states_pre,
                states_post_sym,
            )(pre_states_cx, post_states_cx)

        @staticmethod
        def com_velocity_equality(multinode_penalty, all_pn):
            """
            The centers of mass velocity are equals for the specified phases and the specified nodes

            Parameters
            ----------
            multinode_penalty : MultinodePenalty
                A reference to the phase transition
            all_pn: PenaltyNodeList
                    The penalty node elements

            Returns
            -------
            The difference between the state after and before
            """

            nlp_pre, nlp_post = all_pn[0].nlp, all_pn[1].nlp
            states_pre = multinode_penalty.states_mapping.to_second.map(nlp_pre.states.cx_end)
            states_post = multinode_penalty.states_mapping.to_first.map(nlp_post.states.cx)

            states_post_sym_list = [MX.sym(f"{key}", *nlp_post.states[key].mx.shape) for key in nlp_post.states.keys()]
            states_post_sym = vertcat(*states_post_sym_list)

            if states_pre.shape != states_post.shape:
                raise RuntimeError(
                    f"Continuity can't be established since the number of x to be matched is {states_pre.shape} in the "
                    f"pre-transition phase and {states_post.shape} post-transition phase. Please use a custom "
                    f"transition or supply states_mapping"
                )

            pre_com_dot = nlp_pre.model.CoMdot(
                states_pre[nlp_pre.states["q"].index, :], states_pre[nlp_pre.states["qdot"].index, :]
            ).to_mx()
            post_com_dot = nlp_post.model.CoMdot(states_post_sym_list[0], states_post_sym_list[1]).to_mx()

            pre_states_cx = nlp_pre.states.cx_end
            post_states_cx = nlp_post.states.cx

            return biorbd.to_casadi_func(
                "com_dot_equality",
                pre_com_dot - post_com_dot,
                states_pre,
                states_post_sym,
            )(pre_states_cx, post_states_cx)

        @staticmethod
        def custom(multinode_penalty, all_pn, **extra_params):
            """
            Calls the custom transition function provided by the user

            Parameters
            ----------
            multinode_penalty: MultinodePenalty
                A reference to the phase transition
            all_pn: PenaltyNodeList
                    The penalty node elements

            Returns
            -------
            The expected difference between the last and first node provided by the user
            """

            nlp_pre, nlp_post = all_pn[0].nlp, all_pn[1].nlp
            return multinode_penalty.custom_function(multinode_penalty, nlp_pre, nlp_post, **extra_params)


class MultinodePenaltyFcn(Enum):
    """
    Selection of valid multinode penalty functions
    """

    EQUALITY = (MultinodePenaltyFunctions.Functions.equality,)
    CUSTOM = (MultinodePenaltyFunctions.Functions.custom,)
    COM_EQUALITY = (MultinodePenaltyFunctions.Functions.com_equality,)
    COM_VELOCITY_EQUALITY = (MultinodePenaltyFunctions.Functions.com_velocity_equality,)

    @staticmethod
    def get_type():
        """
        Returns the type of the penalty
        """

        return MultinodePenaltyFunctions
