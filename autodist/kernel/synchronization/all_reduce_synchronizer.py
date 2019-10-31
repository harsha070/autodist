"""AllReduce Synchronizer."""
from tensorflow.python import ops
from tensorflow.python.framework import device_spec
from tensorflow.python.ops import collective_ops

from autodist.kernel.common.utils import get_consumers, update_consumers, \
    replica_prefix
from autodist.kernel.common.utils import get_op_name
from autodist.kernel.synchronization.synchronizer import Synchronizer
from autodist.kernel.synchronization.collective_key import get_collective_keys


class AllReduceSynchronizer(Synchronizer):
    """
    AllReduce Synchronizer.

    The class AllReduceSynchronizer class contains the following possible instantiations:
    (1) spec='auto': single-node multiple devices, or cross-node AllReduce based on collective ops
    (2) spec='nccl': single-node multiple devices, or cross-node AllReduce based on NCCL
    (3) spec='ring'/'tree', Allreduce with different reduction structures: ring, tree, etc.
    However note that it does not contain the following instantiations:
    (1) shuffle reduce (reduce to CPU or GPU as in PS) + Allreduce across nodes
    (2) any other types of hybrid reduction of PS and Allreduce.
    """

    def __init__(self, spec):
        self._spec = spec
        super().__init__()

    def in_graph_apply(self, graph_item, var_name):
        """
        Perform in-graph synchronization based on AllReduce and TensorFlow Collective Ops.

        Note that collective ops now only supports dense tensors.

        Args:
            graph_item: the graph_item to be distributed
            var_name: the corresponded variable name

        Returns:
            GraphItem
        """
        item = graph_item.copy()
        var_op_name = get_op_name(var_name)

        # Throw an error if the variable is sparse
        master_op_name = ops.prepend_name_scope(var_op_name, replica_prefix(0))
        grad, _, _ = graph_item.var_op_name_to_grad_info[master_op_name]
        if isinstance(grad, ops.IndexedSlices):
            raise ValueError('AllReduce synchronizer only supports dense gradients; \
                              PS is recommended for sparse updates.')

        with item.graph.as_default():
            self._share_initializer(item, var_op_name, master_replica=0)
            self._aggregate_gradients(item, var_op_name)
        return item

    def _aggregate_gradients(self, graph_item, var_op_name):
        """Append collective ops after the gradient is calculated."""
        for i in range(0, self.num_replicas):
            op_name = ops.prepend_name_scope(var_op_name, replica_prefix(i))
            grad, _, _ = graph_item.var_op_name_to_grad_info[op_name]
            # TODO (Tairui): (3) Merge of reduction for performance
            grad_consumers = get_consumers(grad.op)  # this line must happen before the next line
            with ops.name_scope(replica_prefix(i)):
                with ops.colocate_with(grad.op):
                    reduced_grad = collective_ops.all_reduce(
                        grad,
                        self.num_replicas * self.num_workers,
                        get_collective_keys().get_group_key(self.all_canonical_replica_devices),
                        get_collective_keys().get_instance_key(var_op_name),
                        'Add',
                        'Div')  # TODO(Hao): add in next TF version -- communication_hint = 'nccl'
            update_consumers(grad_consumers, grad, reduced_grad)
            # TODO(Hao): update grad, target pair here or not?

    def _share_initializer(self, graph_item, var_op_name, master_replica=0):
        """Share the initializers of all replica variables to use initializer on replica=master_replica."""
        # find the initial value of the var on master_replica
        master_var_op = graph_item.graph.get_operation_by_name(
            ops.prepend_name_scope(var_op_name, replica_prefix(master_replica)))
        master_var = graph_item.trainable_var_op_to_var[master_var_op]
        master_init_tensor = graph_item.graph.get_tensor_by_name(master_var.initial_value.name)
        master_init_op = master_init_tensor.op
        # set the device of the init ops to reside on the chief device
        master_init_device = device_spec.DeviceSpecV2.from_string(master_init_op.device)\
            .replace(task=0)
        master_init_op._set_device_from_string(master_init_device.to_string())

        for i in range(0, self.num_replicas):
            if i == master_replica:
                continue
            var_op = graph_item.graph.get_operation_by_name(
                ops.prepend_name_scope(var_op_name, replica_prefix(i)))
            var = graph_item.trainable_var_op_to_var[var_op]
            init_op = graph_item.graph.get_tensor_by_name(var.initial_value.name).op
            init_assign_op = get_consumers(init_op)[0]
            init_assign_op._update_input(1, master_init_tensor)

    def between_graph_apply(self, *args, **kwargs):
        """Allreduce synchronizer will do nothing in between-graph synchronization."""
        # pylint: disable=no-self-use
        # TODO (Hao): improve the signature after refactoring between_graph_apply signatures.
        return None