import unittest
from aipictures.workflow_library import inspect_workflow, dependency_summary


class LibraryChecks(unittest.TestCase):
    def test_missing_weights_and_inputs_are_reported_separately(self):
        graph = {'nodes': [
            {'id': 1, 'type': 'ControlNetLoader', 'widgets_values': ['pose.safetensors']},
            {'id': 2, 'type': 'LoadImage', 'widgets_values': ['reference.png', 'image']}], 'links': []}
        info = {'ControlNetLoader': {'input': {'required': {'control_net_name': [[]]}}},
                'LoadImage': {'input': {'required': {'image': [['different.png']]}}}}
        report = inspect_workflow(graph, info)
        self.assertEqual(report['missing_models'], ['pose.safetensors'])
        self.assertEqual(report['missing_images'], ['reference.png'])
        self.assertFalse(report['dependencies_ready'])
        self.assertIn('pose.safetensors', dependency_summary(report))

    def test_dangling_connection_is_not_treated_as_ready(self):
        graph = {'nodes': [{'id': 1, 'type': 'SaveImage', 'widgets_values': ['output']}],
                 'links': [[1, 999, 0, 1, 0, 'IMAGE']]}
        report = inspect_workflow(graph, {'SaveImage': {}})
        self.assertFalse(report['dependencies_ready'])
        self.assertTrue(report['structural_errors'])


if __name__ == '__main__': unittest.main()
