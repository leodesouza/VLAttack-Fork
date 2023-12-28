"""The Projected Gradient Descent attack."""
import numpy as np
import torch
from torchvision import transforms
from cleverhans.torch.attacks.CLIP.fast_gradient_method_FDA import fast_gradient_method
from cleverhans.torch.utils import clip_eta
import copy
import torch.nn.functional as F

def projected_gradient_descent(
    model_fn,
    x,
    eps,
    eps_iter,
    nb_iter,
    norm,
    clip_min=None,
    clip_max=None,
    y=None,
    ori_x=None,
    time=None,
    targeted=False,
    rand_init=True,
    rand_minmax=None,
    sanity_checks=True,
        ls=None,
    method=None,
    model=None
):
    """
    This class implements either the Basic Iterative Method
    (Kurakin et al. 2016) when rand_init is set to False. or the
    Madry et al. (2017) method if rand_init is set to True.
    Paper link (Kurakin et al. 2016): https://arxiv.org/pdf/1607.02533.pdf
    Paper link (Madry et al. 2017): https://arxiv.org/pdf/1706.06083.pdf
    :param model_fn: a callable that takes an input tensor and returns the model logits.
    :param x: input tensor.
    :param eps: epsilon (input variation parameter); see https://arxiv.org/abs/1412.6572.
    :param eps_iter: step size for each attack iteration
    :param nb_iter: Number of attack iterations.
    :param norm: Order of the norm (mimics NumPy). Possible values: np.inf, 1 or 2.
    :param clip_min: (optional) float. Minimum float value for adversarial example components.
    :param clip_max: (optional) float. Maximum float value for adversarial example components.
    :param y: (optional) Tensor with true labels. If targeted is true, then provide the
              target label. Otherwise, only provide this parameter if you'd like to use true
              labels when crafting adversarial samples. Otherwise, model predictions are used
              as labels to avoid the "label leaking" effect (explained in this paper:
              https://arxiv.org/abs/1611.01236). Default is None.
    :param targeted: (optional) bool. Is the attack targeted or untargeted?
              Untargeted, the default, will try to make the label incorrect.
              Targeted will instead try to move in the direction of being more like y.
    :param rand_init: (optional) bool. Whether to start the attack from a randomly perturbed x.
    :param rand_minmax: (optional) bool. Support of the continuous uniform distribution from
              which the random perturbation on x was drawn. Effective only when rand_init is
              True. Default equals to eps.
    :param sanity_checks: bool, if True, include asserts (Turn them off to use less runtime /
              memory or for unit tests that intentionally pass strange input)
    :return: a tensor for the adversarial example
    """
    if norm == 1:
        raise NotImplementedError(
            "It's not clear that FGM is a good inner loop"
            " step for PGD when norm=1, because norm=1 FGM "
            " changes only one pixel at a time. We need "
            " to rigorously test a strong norm=1 PGD "
            "before enabling this feature."
        )
    if norm not in [np.inf, 2]:
        raise ValueError("Norm order must be either np.inf or 2.")
    if eps < 0:
        raise ValueError(
            "eps must be greater than or equal to 0, got {} instead".format(eps)
        )
    if eps == 0:
        return x
    if eps_iter < 0:
        raise ValueError(
            "eps_iter must be greater than or equal to 0, got {} instead".format(
                eps_iter
            )
        )
    if eps_iter == 0:
        return x
    assert eps_iter <= eps, (eps_iter, eps)
    if clip_min is not None and clip_max is not None:
        if clip_min > clip_max:
            raise ValueError(
                "clip_min must be less than or equal to clip_max, got clip_min={} and clip_max={}".format(
                    clip_min, clip_max
                )
            )

    asserts = []
    # If a data range was specified, check that the input was in that range
    if clip_min is not None:
        assert_ge = torch.all(
            torch.ge(x, torch.tensor(clip_min, device=x.device, dtype=x.dtype))
        )
        asserts.append(assert_ge)

    if clip_max is not None:
        assert_le = torch.all(
            torch.le(x, torch.tensor(clip_max, device=x.device, dtype=x.dtype))
        )
        asserts.append(assert_le)

    # Initialize loop variables
    if time==0:
        rand_init=True
    else:
        rand_init=False
    if rand_init:
        if rand_minmax is None:
            rand_minmax = eps
        eta = torch.zeros_like(x).uniform_(-rand_minmax, rand_minmax)
    else:
        eta = torch.zeros_like(x)
    eta = clip_eta(eta, norm, eps)
    adv_x = x + eta
    if clip_min is not None or clip_max is not None:
        adv_x = torch.clamp(adv_x, clip_min, clip_max)

    if y is None:
        _, y = torch.max(model_fn(x), 1)
    i = 0
    loss_list=[]
    ori_x=ori_x.requires_grad_(False)
    np.random.seed(0)
    f_adv=[]
    y_copy = copy.deepcopy(y)  
    if len(y_copy[0])==12:
        for i, feats_ori in enumerate(y_copy[0]):
            f_adv.append(torch.stack(
                [torch.mean(feats_ori, dim=-1), ] * 768, -1))
        mean_tensors =[f_adv[i] for i in range(12)]
    else:

        for i,feats_ori in enumerate(y_copy[0]):
            f_adv.append(torch.stack([torch.mean(feats_ori.view(1,256*(2**i),-1).permute(0,2,1),dim=-1),]*(256*(2**i)),-1))
        mean_tensors=[f_adv[0],f_adv[1],f_adv[2],f_adv[3]]
    while i < nb_iter:
        adv_x,loss = fast_gradient_method(
            model_fn,
            adv_x,
            eps_iter,
            norm,
            ori_x,
            clip_min=clip_min,
            clip_max=clip_max,
            y=y,
            targeted=targeted,
            mean_tensors=mean_tensors,
        )
        loss_list.append(float(loss.detach().cpu().numpy()))
        eta = adv_x - ori_x
        eta = clip_eta(eta, norm, eps)
        adv_x = ori_x + eta
        if clip_min is not None or clip_max is not None:
            adv_x = torch.clamp(adv_x, clip_min, clip_max)
        i += 1

    asserts.append(eps_iter <= eps)
    if norm == np.inf and clip_min is not None:
        # TODO necessary to cast clip_min and clip_max to x.dtype?
        asserts.append(eps + clip_min <= clip_max)
    asserts=[i.cpu() for i in asserts if i is not True]
    if sanity_checks:
        assert np.all(asserts)
    return adv_x,loss_list